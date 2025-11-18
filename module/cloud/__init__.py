import os
import sys

# debugging purpose only
if __name__ == "__main__":
    sys.path.insert(0, "C:/Users/Patrick/Desktop/Workfile/March7thAssistantClone")

import json
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from module.config import cfg
from module.logger import log

class CloudGameManager:
    LOGIN_ELEMENT_ID = "user-profile"
    COOKIE_PATH = "cookies.json"
    GAME_URL = "https://sr.mihoyo.com/cloud"
    MAX_RETRIES = 3  # 网络异常重试次数

    def __init__(self):
        self.driver = None
        self.headless_mode = cfg.get_value('browser_headless_mode') or False
    
    def _wait_game_page_loaded(self, timeout=5):
        if not self.driver:
            return
        for retry in range(self.MAX_RETRIES):
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#app > div.home-wrapper > picture"))
                )
                return  # 成功加载，直接返回
            except Exception:
                log.warning(f"页面加载超时，正在刷新重试... ({retry + 1}/{self.MAX_RETRIES})")
                try:
                    self.driver.refresh()
                except Exception as e:
                    log.warning(f"刷新失败: {e}")
                sleep(1)

        # 连续 max_retry 次失败
        log.error("页面加载失败，多次刷新无效，程序退出。")
        exit(1)

    def _create_browser(self, browser_type='chrome', headless=False):
        browser_type = cfg.get_value('browser_type') or browser_type
        browser_use_remote = cfg.get_value('browser_use_remote') or False
        if browser_use_remote:
            browser_address = cfg.get_value('browser_remote_address')
            if not browser_address:
                log.error("远程浏览器地址未配置，程序退出。")
                exit(1)
        
        browser_map = ['chrome', 'edge']
        if browser_type not in browser_map:
            log.error(f"不支持的浏览器类型: {browser_type}")
            exit(1)

        options = {
            'chrome': ChromeOptions(),
            'edge': EdgeOptions()
        }[browser_type]

        service = {
            'chrome': ChromeService(log_path=os.devnull),
            'edge': EdgeService(log_path=os.devnull)
        }[browser_type]
        
        if headless:
            options.add_argument("--headless=new")

        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--log-level=3")
        options.add_argument(f"--app={self.GAME_URL}")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        
        if browser_use_remote:
            self.driver = webdriver.Remote(
                command_executor=browser_address,
                options=options
            )
        else:
            self.driver = webdriver.__dict__[browser_type.capitalize()](service=service, options=options)
                
        self.driver.set_window_size(1980, 1080)
        self.driver.execute_cdp_cmd("Emulation.setLocaleOverride", {
            "locale": "zh-CN"
        })
        
        self.confirm_resolution()

        self._get_game_page()
        self._load_cookies()
        self._refresh_page()
            
    def _restart_browser(self, headless=False):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                log.warning(f"退出浏览器异常: {e}")
            self.driver = None
        self._create_browser(headless=headless)
        
    def _save_cookies(self): 
        if not self.driver:
            return
        try:
            cookies = self.driver.get_cookies()
            with open(self.COOKIE_PATH, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=4)
            log.info("登录信息保存成功。")
        except Exception as e:
            log.error(f"保存 cookies 失败: {e}")
            exit(1)

    def _load_cookies(self):
        if not self.driver:
            return False
        try:
            with open(self.COOKIE_PATH, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass  # 忽略无效 cookie

            self.driver.refresh()
            log.info("登录信息加载成功。")
            return True
        except FileNotFoundError:
            log.info("cookies 文件不存在。")
            return False
        except Exception as e:
            log.error(f"加载 cookies 失败: {e}")
            return False

    
    def _get_game_page(self, url = GAME_URL):
        if self.driver:
            self.driver.get(url)
            self._wait_game_page_loaded()
    
    def _refresh_page(self):
        if self.driver:
            self.driver.refresh()
            self._wait_game_page_loaded()

    def _check_login(self, timeout=5):
        if not self.driver:
            return None
        
        logged_in_selector = "#app > div.home-wrapper > div.welcome > div.welcome-wrapper > div > div.user-aid.wel-card__aid"
        not_logged_in_selector = "mihoyo-login-platform-iframe"

        try:
            state = WebDriverWait(self.driver, timeout).until(
                lambda d: (
                    "logged_in"
                    if d.find_elements(By.CSS_SELECTOR, logged_in_selector)
                    else (
                        "not_logged_in"
                        if d.find_elements(By.ID, not_logged_in_selector)
                        else None
                    )
                )
            )

            return state == "logged_in"
        except TimeoutException:
            log.warning("检测登录状态超时：未出现登录或未登录标志元素")
            return None
    
    # 清理页面弹窗
    def _clean_page(self, timeout=2):
        if not self.driver:
            return
        try:
            close_button_selector = "body > div.van-popup.van-popup--center.van-dialog.van-dialog--round-button.clg-confirm-dialog.font-dynamic.clg-dialog-z-index > div.van-action-bar.van-safe-area-bottom.van-dialog__footer > button.van-button.van-button--warning.van-button--large.van-action-bar-button.van-action-bar-button--warning.van-action-bar-button--first.van-dialog__cancel"
            try:
                close_button = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, close_button_selector))
                )
            except TimeoutException:
                log.info("未检测到弹窗，无需关闭。")
                return
            
            close_button.click()
            log.info("关闭弹窗成功。")
        except Exception as e:
            log.error(f"关闭弹窗异常: {e}")
            
    def _click_enter_game(self, timeout=5):
        if not self.driver:
            return
        try:
            enter_button_selector = "#app > div.home-wrapper > div.welcome > div.welcome-wrapper > div > div.wel-card__content > div.wel-card__content--start"
            enter_button = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, enter_button_selector))
            )
            enter_button.click()
        except Exception as e:
            log.error(f"点击进入游戏按钮游戏异常: {e}")
            raise e
        
    def _wait_in_queue(self, timeout=600):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, ".waiting-in-queue"))
            )
        except TimeoutError as e:
            log.error("等待排队超时")
        except Exception as e:
            log.error(f"等待排队异常: {e}") 

    def start_game(self):
        if not self.driver:
            self._create_browser(headless=self.headless_mode)
        
        for attempt in range(self.MAX_RETRIES):
            try:
                self._get_game_page()
                # 自动检测登录状态
                while not self._check_login():
                    log.info("未登录")
                    if self.headless_mode:
                        self._restart_browser(headless=False)
                    log.info("请在浏览器中完成登录操作")
                    
                    while not self._check_login():
                        sleep(2)
                        
                    log.info("检测到登录成功")
                    
                    self._save_cookies()
                    if self.headless_mode:
                        self._restart_browser(headless=self.headless_mode)
                        
                # 启动游戏
                self._clean_page()
                self._click_enter_game()
                sleep(1)
                self._wait_in_queue(cfg.get_value("max_queue_time"))
                self.confirm_resolution()
                
                log.info("云游戏启动成功")
                        
                return True 
            except Exception as e:
                log.warning(f"启动游戏失败（尝试 {attempt + 1}/{self.MAX_RETRIES}）: {e}")
                self._restart_browser(headless=self.headless_mode)
                sleep(1)
        log.error("启动游戏失败，超过最大重试次数。")
        return False
    
    def confirm_resolution(self):
        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080,
            "deviceScaleFactor": 1,
            "mobile": False
        })
    
    def take_screenshot(self):
        # self.confirm_resolution()
        png = self.driver.get_screenshot_as_png()
        with open("screenshot.png", "wb") as f: #TODO debug only
                f.write(png)
        return png
    
    def execute_cdp_cmd(self, cmd: str, cmd_args: dict):
        return self.driver.execute_cdp_cmd(cmd, cmd_args)

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                log.warning(f"退出浏览器异常: {e}")
            self.driver = None
            
cloud_game: CloudGameManager = CloudGameManager()

if __name__ == "__main__":
    from module.automation.browser_input import BrowserInput
    from module.logger import log

    cloud_game.start_game()
    b_input = BrowserInput(cloud_game, log)

    print("=== BrowserInput 测试工具 ===")
    print("输入键名测试按键，例如: esc, enter, a-z, 0-9, f1-f12")
    print("输入 mouse_move x y | mouse_click x y | mouse_scroll count direction")
    print("输入 secretly_press key | secretly_write text")
    print("输入 exit 退出\n")

    try:
        while True:
            cmd = input(">>> ").strip()
            if not cmd:
                continue
            if cmd.lower() in ("exit", "quit"):
                break

            parts = cmd.split()
            action = parts[0].lower()

            try:
                if action in b_input.SPECIAL_KEY_MAP or action in b_input.CHAR_KEY_MAP:
                    # 直接按键测试
                    b_input.press_key(action)
                elif action == "mouse_move" and len(parts) == 3:
                    x, y = int(parts[1]), int(parts[2])
                    b_input.mouse_move(x, y)
                elif action == "mouse_click" and len(parts) == 3:
                    x, y = int(parts[1]), int(parts[2])
                    b_input.mouse_click(x, y)
                elif action == "mouse_scroll" and len(parts) >= 2:
                    count = int(parts[1])
                    direction = int(parts[2]) if len(parts) >= 3 else -1
                    b_input.mouse_scroll(count, direction)
                elif action == "secretly_press" and len(parts) == 2:
                    b_input.secretly_press_key(parts[1])
                elif action == "secretly_write" and len(parts) >= 2:
                    text = " ".join(parts[1:])
                    b_input.secretly_write(text)
                else:
                    print("未知命令或参数错误")
            except Exception as e:
                print(f"执行出错: {e}")

    except KeyboardInterrupt:
        print("\n退出测试")