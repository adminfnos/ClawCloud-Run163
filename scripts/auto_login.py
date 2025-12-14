#!/usr/bin/env python3
"""
ClawCloud 自动登录脚本
功能：使用 GitHub Token 自动登录，并通过 Telegram 发送通知
"""

import os
import sys
import time
import json
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ==================== 配置 ====================
CLAW_CLOUD_URL = "https://eu-central-1.run.claw.cloud"
SIGNIN_URL = f"{CLAW_CLOUD_URL}/signin"


class TelegramNotifier:
    """Telegram 通知类"""
    
    def __init__(self):
        self.bot_token = os.environ.get('TG_BOT_TOKEN')
        self.chat_id = os.environ.get('TG_CHAT_ID')
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            print("⚠️ Telegram 通知未配置，跳过通知功能")
    
    def send_message(self, message):
        """发送文本消息"""
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"发送 Telegram 消息失败: {e}")
            return False
    
    def send_photo(self, photo_path, caption=""):
        """发送图片"""
        if not self.enabled:
            return False
        
        if not os.path.exists(photo_path):
            print(f"图片不存在: {photo_path}")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            with open(photo_path, 'rb') as photo:
                data = {"chat_id": self.chat_id, "caption": caption}
                files = {"photo": photo}
                response = requests.post(url, data=data, files=files, timeout=60)
            return response.status_code == 200
        except Exception as e:
            print(f"发送 Telegram 图片失败: {e}")
            return False
    
    def send_document(self, file_path, caption=""):
        """发送文件"""
        if not self.enabled:
            return False
        
        if not os.path.exists(file_path):
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
            with open(file_path, 'rb') as doc:
                data = {"chat_id": self.chat_id, "caption": caption}
                files = {"document": doc}
                response = requests.post(url, data=data, files=files, timeout=60)
            return response.status_code == 200
        except Exception as e:
            print(f"发送 Telegram 文件失败: {e}")
            return False


class AutoLogin:
    """自动登录类"""
    
    def __init__(self):
        self.username = os.environ.get('GH_USERNAME')
        self.token = os.environ.get('GH_PAT')
        self.debug = os.environ.get('DEBUG_MODE', 'true').lower() == 'true'
        self.screenshot_count = 0
        self.screenshots = []  # 保存所有截图路径
        self.telegram = TelegramNotifier()
        self.logs = []  # 保存日志用于通知
        
    def log(self, message, level="INFO"):
        """打印日志"""
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅", 
            "ERROR": "❌",
            "WARN": "⚠️",
            "STEP": "🔹"
        }
        log_line = f"{icons.get(level, '•')} {message}"
        print(log_line)
        self.logs.append(log_line)
    
    def screenshot(self, page, name):
        """保存截图"""
        self.screenshot_count += 1
        filename = f"{self.screenshot_count:02d}_{name}.png"
        page.screenshot(path=filename)
        self.screenshots.append(filename)
        self.log(f"截图已保存: {filename}")
        return filename
    
    def validate_credentials(self):
        """验证凭据"""
        if not self.username:
            self.log("错误：未设置 GH_USERNAME", "ERROR")
            return False
        if not self.token:
            self.log("错误：未设置 GH_PAT", "ERROR")
            return False
        self.log(f"用户名: {self.username}")
        self.log(f"Token: {'*' * 10}...{self.token[-4:]}")
        return True
    
    def find_and_click(self, page, selectors, description="元素"):
        """查找并点击元素"""
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=3000):
                    element.click()
                    self.log(f"已点击: {description}", "SUCCESS")
                    return True
            except:
                continue
        return False
    
    def check_github_error(self, page):
        """检查 GitHub 登录错误"""
        error_selectors = [
            '.flash-error',
            '.flash.flash-error',
            '#js-flash-container .flash-error',
        ]
        
        for selector in error_selectors:
            try:
                error_el = page.locator(selector).first
                if error_el.is_visible(timeout=1000):
                    return error_el.inner_text()
            except:
                continue
        return None
    
    def check_device_verification(self, page):
        """检查是否需要设备验证"""
        if 'sessions/verified-device' in page.url or 'device-verification' in page.url:
            return True
        
        content = page.content().lower()
        keywords = ['verify your device', 'device verification', 'check your email', 'verification code']
        return any(kw in content for kw in keywords)
    
    def check_2fa(self, page):
        """检查是否需要两步验证"""
        if 'two-factor' in page.url:
            return True
        
        try:
            otp_field = page.locator('input[name="otp"], input[name="app_otp"], #otp')
            return otp_field.is_visible(timeout=2000)
        except:
            return False
    
    def login_github(self, page):
        """登录 GitHub"""
        self.log("正在登录 GitHub...", "STEP")
        self.screenshot(page, "github_登录页")
        
        # 填写凭据
        try:
            page.locator('input[name="login"]').fill(self.username)
            self.log("已输入用户名")
            
            page.locator('input[name="password"]').fill(self.token)
            self.log("已输入 Token")
        except Exception as e:
            self.log(f"输入凭据失败: {e}", "ERROR")
            return False
        
        self.screenshot(page, "github_已填写凭据")
        
        # 点击登录
        try:
            page.locator('input[type="submit"], button[type="submit"]').first.click()
            self.log("已点击登录按钮")
        except Exception as e:
            self.log(f"点击登录失败: {e}", "ERROR")
            return False
        
        time.sleep(3)
        page.wait_for_load_state('networkidle', timeout=30000)
        self.screenshot(page, "github_登录后")
        
        current_url = page.url
        self.log(f"当前页面: {current_url}")
        
        # 检查错误
        error = self.check_github_error(page)
        if error:
            self.log(f"GitHub 错误: {error}", "ERROR")
            return False
        
        # 检查设备验证
        if self.check_device_verification(page):
            self.log("需要设备验证！GitHub 检测到新设备，已发送验证邮件。", "ERROR")
            self.log("请先手动登录一次 GitHub 完成设备验证。", "WARN")
            self.screenshot(page, "github_设备验证")
            return False
        
        # 检查两步验证
        if self.check_2fa(page):
            self.log("需要两步验证！此脚本无法自动处理 2FA。", "ERROR")
            self.screenshot(page, "github_两步验证")
            return False
        
        # 检查是否仍在登录页
        if 'github.com/login' in current_url or 'github.com/session' in current_url:
            self.log("仍在 GitHub 登录页面，登录可能失败", "WARN")
            
            page_content = page.content()
            if 'Incorrect username or password' in page_content:
                self.log("用户名或密码错误！", "ERROR")
                return False
            if 'too many' in page_content.lower():
                self.log("登录尝试次数过多，已被限制", "ERROR")
                return False
        
        return True
    
    def handle_oauth(self, page):
        """处理 OAuth 授权"""
        if 'github.com/login/oauth/authorize' in page.url:
            self.log("正在处理 OAuth 授权...", "STEP")
            self.screenshot(page, "oauth_授权页")
            
            authorize_selectors = [
                'button[name="authorize"]',
                'button:has-text("Authorize")',
                '#js-oauth-authorize-btn',
            ]
            
            self.find_and_click(page, authorize_selectors, "授权按钮")
            time.sleep(3)
            page.wait_for_load_state('networkidle', timeout=30000)
        
        return True
    
    def wait_redirect(self, page, max_wait=45):
        """等待重定向到 ClawCloud"""
        self.log(f"等待重定向到 ClawCloud（最多 {max_wait} 秒）...", "STEP")
        
        for i in range(max_wait):
            current_url = page.url
            
            # 成功
            if 'claw.cloud' in current_url and 'signin' not in current_url.lower():
                self.log("成功重定向到 ClawCloud！", "SUCCESS")
                return True
            
            # 失败
            if i > 10 and ('github.com/login' in current_url or 'github.com/session' in current_url):
                self.log("卡在 GitHub 登录页面", "ERROR")
                return False
            
            # 处理 OAuth
            if 'github.com/login/oauth/authorize' in current_url:
                self.handle_oauth(page)
            
            time.sleep(1)
            if i % 5 == 0:
                self.log(f"  等待中... ({i}秒)")
        
        self.log("等待重定向超时", "ERROR")
        return False
    
    def verify_login(self, page, context):
        """验证 ClawCloud 登录状态"""
        current_url = page.url
        title = page.title()
        
        self.log(f"最终页面: {current_url}")
        self.log(f"页面标题: {title}")
        
        if 'claw.cloud' not in current_url:
            self.log("不在 ClawCloud 域名！", "ERROR")
            return False
        
        if 'signin' in current_url.lower() or 'login' in current_url.lower():
            self.log("仍在登录页面，登录失败！", "ERROR")
            return False
        
        # 获取 cookies
        cookies = context.cookies()
        claw_cookies = [c for c in cookies if 'claw' in c.get('domain', '')]
        
        if len(claw_cookies) == 0:
            self.log("未获取到 ClawCloud cookies！", "ERROR")
            return False
        
        self.log(f"已获取 {len(claw_cookies)} 个 ClawCloud cookies", "SUCCESS")
        
        # 保存 cookies
        with open('cookies.json', 'w') as f:
            json.dump(claw_cookies, f, indent=2)
        
        return True
    
    def keepalive(self, page):
        """访问页面保持活跃"""
        self.log("正在访问页面保持账户活跃...", "STEP")
        
        pages = [
            (f"{CLAW_CLOUD_URL}/", "控制台首页"),
            (f"{CLAW_CLOUD_URL}/apps", "应用列表"),
        ]
        
        for url, name in pages:
            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                
                if 'signin' in page.url.lower():
                    self.log(f"访问 {name} 时被重定向到登录页！", "ERROR")
                    return False
                
                self.log(f"已访问: {name}", "SUCCESS")
                time.sleep(2)
            except Exception as e:
                self.log(f"访问 {name} 失败: {e}", "WARN")
        
        self.screenshot(page, "保活完成")
        return True
    
    def send_notification(self, success, error_msg=""):
        """发送 Telegram 通知"""
        if not self.telegram.enabled:
            return
        
        # 构建消息
        status = "✅ 成功" if success else "❌ 失败"
        
        message = f"""
<b>🤖 ClawCloud 自动登录通知</b>

<b>状态:</b> {status}
<b>用户:</b> {self.username}
<b>时间:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        if error_msg:
            message += f"\n<b>错误:</b> {error_msg}"
        
        # 添加最近日志
        recent_logs = self.logs[-10:]  # 最后10条日志
        if recent_logs:
            message += "\n\n<b>📋 最近日志:</b>\n"
            message += "\n".join(recent_logs)
        
        # 发送消息
        self.telegram.send_message(message)
        
        # 发送最后一张截图
        if self.screenshots:
            last_screenshot = self.screenshots[-1]
            caption = "最终截图" if success else "错误截图"
            self.telegram.send_photo(last_screenshot, caption)
            
            # 如果失败，发送所有截图
            if not success and len(self.screenshots) > 1:
                for screenshot in self.screenshots[:-1]:
                    self.telegram.send_photo(screenshot, f"调试截图: {screenshot}")
    
    def run(self):
        """主流程"""
        print("\n" + "="*60)
        print("🚀 ClawCloud 自动登录脚本")
        print("="*60 + "\n")
        
        if not self.validate_credentials():
            self.send_notification(False, "凭据未配置")
            sys.exit(1)
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            )
            
            page = context.new_page()
            
            try:
                # 步骤 1: 访问 ClawCloud
                self.log("步骤 1: 打开 ClawCloud 登录页", "STEP")
                page.goto(SIGNIN_URL, timeout=60000)
                page.wait_for_load_state('networkidle', timeout=30000)
                time.sleep(2)
                
                self.screenshot(page, "clawcloud_登录页")
                
                # 检查是否已登录
                if 'signin' not in page.url.lower():
                    self.log("已经登录！", "SUCCESS")
                    if self.verify_login(page, context):
                        self.keepalive(page)
                        self.send_notification(True)
                        print("\n✅ 成功：已经是登录状态！\n")
                        return
                    else:
                        self.send_notification(False, "验证登录状态失败")
                        sys.exit(1)
                
                # 步骤 2: 点击 GitHub 登录
                self.log("步骤 2: 点击 GitHub 登录按钮", "STEP")
                
                github_selectors = [
                    'button:has-text("GitHub")',
                    'a:has-text("GitHub")',
                    'button:has-text("Continue with GitHub")',
                    '[data-provider="github"]',
                ]
                
                if not self.find_and_click(page, github_selectors, "GitHub 按钮"):
                    self.log("找不到 GitHub 登录按钮", "ERROR")
                    self.screenshot(page, "找不到按钮")
                    self.send_notification(False, "找不到 GitHub 登录按钮")
                    sys.exit(1)
                
                time.sleep(3)
                page.wait_for_load_state('networkidle', timeout=30000)
                self.screenshot(page, "点击github后")
                
                # 步骤 3: GitHub 登录
                self.log("步骤 3: GitHub 身份验证", "STEP")
                
                if 'github.com/login' in page.url or 'github.com/session' in page.url:
                    if not self.login_github(page):
                        self.screenshot(page, "github_登录失败")
                        self.send_notification(False, "GitHub 登录失败")
                        print("\n❌ 失败：GitHub 登录失败！\n")
                        sys.exit(1)
                
                # 步骤 4: 等待重定向
                self.log("步骤 4: 等待重定向", "STEP")
                
                if not self.wait_redirect(page):
                    self.screenshot(page, "重定向失败")
                    self.send_notification(False, "重定向到 ClawCloud 失败")
                    print("\n❌ 失败：无法重定向到 ClawCloud！\n")
                    sys.exit(1)
                
                self.screenshot(page, "重定向成功")
                
                # 步骤 5: 验证登录
                self.log("步骤 5: 验证登录状态", "STEP")
                
                if not self.verify_login(page, context):
                    self.screenshot(page, "验证失败")
                    self.send_notification(False, "登录验证失败")
                    print("\n❌ 失败：登录验证失败！\n")
                    sys.exit(1)
                
                # 步骤 6: 保持活跃
                self.log("步骤 6: 保持账户活跃", "STEP")
                self.keepalive(page)
                
                # 发送成功通知
                self.send_notification(True)
                
                print("\n" + "="*60)
                print("✅ 自动登录成功！")
                print("="*60 + "\n")
                
            except Exception as e:
                self.log(f"发生异常: {e}", "ERROR")
                self.screenshot(page, "异常")
                import traceback
                traceback.print_exc()
                self.send_notification(False, str(e))
                sys.exit(1)
            
            finally:
                browser.close()


if __name__ == "__main__":
    login = AutoLogin()
    login.run()
