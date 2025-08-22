import re
import random
import string
import hashlib
import pymysql
from astrbot import Plugin, on_event, on_message

# 数据库配置，需根据实际环境修改
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_db_user',
    'password': 'your_db_password',
    'charset': 'utf8mb4'
}

# 初始赠送的货币数量
INITIAL_CERA = 1000  # 点券
INITIAL_CERA_POINT = 500  # 代币

class GameAccountPlugin(Plugin):
    """游戏账号管理插件，实现自动同意好友请求和账号注册修改功能"""
    
    def __init__(self):
        super().__init__()
        self.db = self._get_db_connection()
        if not self.db:
            self.logger.error("数据库连接初始化失败，插件功能将受限")
    
    def _get_db_connection(self):
        """获取数据库连接"""
        try:
            conn = pymysql.connect(
                host=DB_CONFIG['host'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                charset=DB_CONFIG['charset']
            )
            return conn
        except Exception as e:
            self.logger.error(f"数据库连接失败: {str(e)}")
            return None
    
    def _md5_encrypt(self, text):
        """对文本进行MD5加密"""
        md5 = hashlib.md5()
        md5.update(text.encode('utf-8'))
        return md5.hexdigest()
    
    def _generate_random_password(self):
        """生成6位数字+字母的随机密码"""
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(6))
    
    def _generate_11_digits(self):
        """生成11位纯数字"""
        return ''.join(str(random.randint(0, 9)) for _ in range(11))
    
    def _check_account_exists(self, qq):
        """检查账号是否已注册"""
        if not self.db:
            return False, "数据库连接失败"
        
        try:
            with self.db.cursor() as cursor:
                sql = "SELECT UID FROM d_taiwan.accounts WHERE accountname = %s LIMIT 1;"
                cursor.execute(sql, (qq,))
                result = cursor.fetchone()
                return True, result is not None
        except Exception as e:
            self.logger.error(f"检查账号存在失败: {str(e)}")
            return False, str(e)
    
    def _register_account(self, qq):
        """执行账号注册流程"""
        if not self.db:
            return False, "数据库连接失败"
        
        try:
            # 生成密码并加密
            password = self._generate_random_password()
            encrypted_password = self._md5_encrypt(password)
            
            # 生成11位数字
            qq_number = self._generate_11_digits()
            
            with self.db.cursor() as cursor:
                # 第四步：执行账号注册
                sql = """
                INSERT INTO d_taiwan.accounts 
                    (accountname, password, qq, ip, seal_IP, seal_MAC, seal_accountname) 
                VALUES 
                    (%s, %s, %s, '0', '0', '0', '0');
                """
                cursor.execute(sql, (qq, encrypted_password, qq_number))
                
                # 第五步：获取新账号UID
                sql = "SELECT UID FROM d_taiwan.accounts WHERE accountname = %s LIMIT 1;"
                cursor.execute(sql, (qq,))
                uid = cursor.fetchone()[0]
                
                # 第六步：插入会员信息
                sql = """
                INSERT INTO d_taiwan.member_info 
                    (m_id, user_id, updt_date, state, email_yn, slot) 
                VALUES 
                    (%s, %s, NOW(), 1, 'y', 8);
                """
                cursor.execute(sql, (uid, uid))
                
                # 第七步：插入会员资料
                sql = """
                INSERT INTO d_taiwan.member_join_info 
                    (m_id, reg_date, ip, contry_code, login_time, error_type, login_ip, game_use_history) 
                VALUES 
                    (%s, 0, '', 0, 0, 0, '', 0);
                """
                cursor.execute(sql, (uid,))
                
                # 第八步：加入白名单
                sql = """
                INSERT INTO d_taiwan.member_white_account 
                    (m_id, reg_date) 
                VALUES 
                    (%s, '0000-00-00 00:00:00');
                """
                cursor.execute(sql, (uid,))
                
                # 第九步：设置登录信息
                sql = """
                INSERT INTO taiwan_login.member_login 
                    (m_id, login_time, expire_time, last_play_time, total_account_fail, account_fail, 
                     report_cnt, reliable_flag, trade_gold_daily, last_gift_time, gift_cnt, login_ip, 
                     security_flag, power_side, dungeon_gain_gold, school_id, rating, cleanpad_point, 
                     tutorial_skipable, event_charac_flag, garena_token_key) 
                VALUES 
                    (%s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, '0', 0, 0);
                """
                cursor.execute(sql, (uid,))
                
                # 第十步：赠送初始货币
                # 点券
                sql = """
                INSERT INTO taiwan_billing.cash_cera 
                    (account, cera, cera_cold, mod_tran, mod_date, reg_date) 
                VALUES 
                    (%s, %s, 0, 0, '0000-00-00 00:00:00', '0000-00-00 00:00:00');
                """
                cursor.execute(sql, (uid, INITIAL_CERA))
                
                # 代币
                sql = """
                INSERT INTO taiwan_billing.cash_cera_point 
                    (account, cera_point, reg_date, mod_date) 
                VALUES 
                    (%s, %s, '0000-00-00 00:00:00', '0000-00-00 00:00:00');
                """
                cursor.execute(sql, (uid, INITIAL_CERA_POINT))
                
                # 提交事务
                self.db.commit()
                
                return True, {
                    'qq': qq,
                    'password': password,
                    'cera': INITIAL_CERA,
                    'cera_point': INITIAL_CERA_POINT
                }
                
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"注册账号失败: {str(e)}")
            return False, str(e)
    
    def _change_password(self, qq, new_password):
        """修改密码处理"""
        if not self.db:
            return False, "数据库连接失败"
        
        # 密码预处理
        new_password = new_password.strip().replace('\n', '').replace('\r', '')
        
        # 密码格式验证
        if not re.match(r'^[a-zA-Z0-9]{3,16}$', new_password):
            if len(new_password) < 3 or len(new_password) > 16:
                return False, "密码仅支持3-16位"
            else:
                return False, "密码不支持符号、中文，请重新输入"
        
        try:
            with self.db.cursor() as cursor:
                # 密码加密
                encrypted_password = self._md5_encrypt(new_password)
                
                # 执行更新
                sql = """
                UPDATE d_taiwan.accounts 
                SET password = %s 
                WHERE accountname = %s;
                """
                cursor.execute(sql, (encrypted_password, qq))
                self.db.commit()
                
                if cursor.rowcount > 0:
                    return True, new_password
                else:
                    return False, "账号不存在或密码未修改"
                    
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"修改密码失败: {str(e)}")
            return False, str(e)
    
    @on_event('friend_request')
    def auto_accept_friend_request(self, event):
        """自动同意好友请求"""
        try:
            event.accept()
            self.logger.info(f"已自动同意QQ {event.qq} 的好友请求")
        except Exception as e:
            self.logger.error(f"自动同意好友请求失败: {str(e)}")
    
    @on_message()
    def handle_message(self, message):
        """处理消息，实现账号注册与密码修改"""
        # 获取消息信息
        sender_qq = message.sender.qq
        content = message.content.strip()
        is_friend = message.is_friend  # 判断是否为好友
        
        # 处理临时会话
        if not is_friend:
            message.reply("如果我们不是好友，发送账号信息会被屏蔽，请添加我之后再注册")
            return
        
        # 处理修改密码请求
        if content.startswith("修改密码"):
            new_password = content[4:].strip()
            success, result = self._change_password(sender_qq, new_password)
            
            if success:
                reply = f"""---------------------------------
账号：{sender_qq}
密码：{result}
密码修改成功
---------------------------------"""
                message.reply(reply)
            else:
                message.reply(result)
            return
        
        # 处理注册请求
        success, exists = self._check_account_exists(sender_qq)
        if not success:
            message.reply(f"操作失败: {exists}")
            return
        
        if exists:
            message.reply("您已注册账号，如需修改密码，请发送【修改密码+新密码】，例如：【修改密码asd123456】")
        else:
            # 执行注册流程
            reg_success, reg_result = self._register_account(sender_qq)
            if reg_success:
                reply = f"""-----------------------------------
账号：{reg_result['qq']}
密码：{reg_result['password']}
赠送：{reg_result['cera']}点券 {reg_result['cera_point']}代币
如要修改密码：发送【修改密码+新密码】
例：【修改密码asd123456】
-----------------------------------"""
                message.reply(reply)
            else:
                message.reply(f"注册失败: {reg_result}")

# 插件出口
plugin = GameAccountPlugin()
