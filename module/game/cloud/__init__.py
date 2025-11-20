import os
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
from selenium.common.exceptions import TimeoutException, SessionNotCreatedException
from selenium.webdriver.common.driver_finder import DriverFinder

from module.config import Config
from module.game.game_controller_base import GameControllerBase
from module.logger import Logger
from utils.encryption import wdp_encrypt, wdp_decrypt

class CloudGameController(GameControllerBase):
    COOKIE_PATH = "cookies.encrypted"
    GAME_URL = "https://sr.mihoyo.com/cloud"
    MAX_RETRIES = 3  # 网络异常重试次数

    def __init__(self, cfg: Config, logger: Logger):
        super().__init__(script_path=cfg.script_path, logger=logger)
        self.driver = None
        self.scripts_to_inject = None
        self.cfg = cfg
        self.logger = logger
    
    def _wait_game_page_loaded(self, timeout=5):
        """等待云崩铁网页加载出来，这里以背景图是否加载出来为准"""
        if not self.driver:
            return
        for retry in range(self.MAX_RETRIES):
            try:
                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.execute_script(
                        """
                        const img = document.querySelector('#app > div.home-wrapper > picture > img');
                        if (!img) return false;
                        return img && img.complete && img.naturalWidth > 0;
                        """
                    )
                )
                return
            except TimeoutException:
                self.log_warning(f"页面加载超时，正在刷新重试... ({retry + 1}/{self.MAX_RETRIES})")
                try:
                    self.driver.refresh()
                except Exception as e:
                    self.log_warning(f"刷新失败: {e}")

        # 连续 max_retry 次失败
        raise Exception("页面加载失败，多次刷新无效。")
        

    def _create_browser(self, headless=False):
        """启动浏览器"""
        browser_type = self.cfg.browser_type
        
        browser_map = ['chrome', 'edge']
        if browser_type not in browser_map:
            self.log_error(f"不支持的浏览器类型: {browser_type}")
            exit(1)

        options = {
            'chrome': ChromeOptions(),
            'edge': EdgeOptions()
        }[browser_type]

        service = {
            'chrome': ChromeService(log_path=os.devnull),
            'edge': EdgeService(log_path=os.devnull)
        }[browser_type]
        
        finder = DriverFinder(service, options)

        self.log_debug(f"浏览器路径：{finder.get_browser_path()}")
        self.log_debug(f"浏览器驱动路径：{finder.get_driver_path()}")
        
        if headless:
            options.add_argument("--headless=new")

        options.add_argument("--lang=zh-CN")
        options.add_argument("--log-level=3")
        options.add_argument(f"--force-device-scale-factor={float(self.cfg.browser_scale_factor)}")
        options.add_argument(f"--app={self.GAME_URL}")
        if self.cfg.cloud_game_full_screen and not self.cfg.browser_headless_mode:
            options.add_argument("--start-fullscreen")
            
        # 去掉提示 "浏览器正由自动测试软件控制。"
        # edge driver 这个选项在管理员模式下存在 bug，会出现 SessionNotCreatedException
        if browser_type == "chrome":
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_argument("--disable-blink-features=AutomationControlled")
        
        for arg in self.cfg.browser_launch_argument:
            options.add_argument(arg)
        
        if self.cfg.browser_use_remote:
            self.driver = webdriver.Remote(
                command_executor=self.cfg.browser_remote_address,
                options=options
            )
        else:
            self.driver = browser_map = {
                "chrome": webdriver.Chrome,
                "edge": webdriver.Edge,
            }[browser_type](service=service, options=options)
                
        self.confirm_viewport_resolution()

        self._get_game_page()
        self._load_local_storage()
        self._load_cookies()
        self._refresh_page()
            
    def _restart_browser(self, headless=False):
        """重启浏览器"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.log_warning(f"退出浏览器异常: {e}")
            self.driver = None
        self._create_browser(headless=headless)
    
    def _load_local_storage(self):
        """加载初始配置"""
        # 先读取模板
        with open("assets/config/local_storage_template.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        # 修改需要同步的字段
        settings = json.loads(data["clgm_web_app_settings_hkrpg_cn"])
        settings["videoMode"] = self.cfg.cloud_game_smooth_first if 1 else 0
        data["clgm_web_app_settings_hkrpg_cn"] = json.dumps(settings)

        client_config = json.loads(data["clgm_web_app_client_store_config_hkrpg_cn"])
        client_config["speedLimitGearId"] = self.cfg.cloud_game_video_quality
        client_config["fabPosition"]["x"] = self.cfg.cloud_game_fab_pos_x
        client_config["fabPosition"]["y"] = self.cfg.cloud_game_fab_pos_y
        client_config["showGameStatBar"] = self.cfg.cloud_game_show_status_bar
        client_config["gameStatBarType"] = self.cfg.cloud_game_status_bar_type
        data["clgm_web_app_client_store_config_hkrpg_cn"] = json.dumps(client_config)

        # 注入浏览器
        for key, value in data.items():
            self.driver.execute_script(
                "window.localStorage.setItem(arguments[0], arguments[1]);",
                key,
                value,
            )
        
    def _save_cookies(self):
        """保存登录信息""" 
        if not self.driver:
            return
        try:
            cookies_json = json.dumps(self.driver.get_cookies(), ensure_ascii=False, indent=4)
            with open(self.COOKIE_PATH, "wb") as f:
                f.write(wdp_encrypt(cookies_json.encode()))
            self.log_info("登录信息保存成功。")
        except Exception as e:
            self.log_error(f"保存 cookies 失败: {e}")

    def _load_cookies(self):
        """加载登录信息"""
        if not self.driver:
            return False
        try:
            with open(self.COOKIE_PATH, "rb") as f:
                cookies = json.loads(wdp_decrypt(f.read()).decode())

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass  # 忽略无效 cookie

            self.driver.refresh()
            self.log_info("登录信息加载成功。")
            return True
        except FileNotFoundError:
            self.log_info("cookies 文件不存在。")
            return False
        except Exception as e:
            self.log_error(f"加载 cookies 失败: {e}")
            return False

    
    def _get_game_page(self, url = GAME_URL):
        if self.driver:
            self.driver.get(url)
            self._inject_scripts()
            self._wait_game_page_loaded()
    
    def _refresh_page(self):
        if self.driver:
            self.driver.refresh()
            self._wait_game_page_loaded()

    def _check_login(self, timeout=5):
        """检查是否已经登录"""
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
            self.log_warning("检测登录状态超时：未出现登录或未登录标志元素")
            return None
    
    def _clean_page(self, timeout=2):
        """清理页面弹窗"""
        if not self.driver:
            return
        try:
            close_button_selector = "body > div.van-popup.van-popup--center.van-dialog.van-dialog--round-button.clg-confirm-dialog.font-dynamic.clg-dialog-z-index > div.van-action-bar.van-safe-area-bottom.van-dialog__footer > button.van-button.van-button--warning.van-button--large.van-action-bar-button.van-action-bar-button--warning.van-action-bar-button--first.van-dialog__cancel"
            try:
                close_button = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, close_button_selector))
                )
            except TimeoutException:
                self.log_info("未检测到弹窗，无需关闭。")
                return
            
            close_button.click()
            self.log_info("关闭弹窗成功。")
        except Exception as e:
            self.log_error(f"关闭弹窗异常: {e}")
            
    def _click_enter_game(self, timeout=5):
        """点击‘进入游戏’按钮"""
        if not self.driver:
            return
        try:
            enter_button_selector = "#app > div.home-wrapper > div.welcome > div.welcome-wrapper > div > div.wel-card__content > div.wel-card__content--start"
            enter_button = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, enter_button_selector))
            )
            enter_button.click()
        except Exception as e:
            self.log_error(f"点击进入游戏按钮游戏异常: {e}")
            raise e
        
    def _wait_in_queue(self, timeout=600):
        """排队等待进入"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, ".waiting-in-queue"))
            )
        except TimeoutError as e:
            self.log_error("等待排队超时")
        except Exception as e:
            self.log_error(f"等待排队异常: {e}")
            
    def _inject_scripts(self):
        if self.scripts_to_inject:
            self.driver.execute_script(self.scripts_to_inject)
        
    def set_inject_scripts(self, scripts):
        self.scripts_to_inject = scripts
        
    #patrick: debug only
    def dump_page(self, dump_dir="dump"):
        os.makedirs(dump_dir, exist_ok=True)
        import datetime
        # 时间戳
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存截图
        png_path = os.path.join(dump_dir, f"{ts}.png")
        self.driver.save_screenshot(png_path)

        # 保存 HTML
        html_path = os.path.join(dump_dir, f"{ts}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)

        print("已保存：", png_path, html_path)
        
    def start_game(self):
        """启动游戏"""
    
        for attempt in range(self.MAX_RETRIES):
            try:
                if not self.driver:
                    self._create_browser(headless=self.cfg.browser_headless_mode)

                self._get_game_page()
                
                # 检测登录状态
                while not self._check_login():
                    self.log_info("未登录")
                    
                    # 如果是 headless，则以非 headless 模式重启启动让用户登录
                    if self.cfg.browser_headless_mode:
                        self._restart_browser(headless=False)
                        
                    self.log_info("请在浏览器中完成登录操作")
                    
                    # 循环检测用户是否登录
                    while not self._check_login():
                        sleep(2)
                        
                    self.log_info("检测到登录成功")
                    
                    # 保存用户信息
                    self._save_cookies()
                    
                    # 如果为 headless 模式，则重启浏览器回到 headless 模式
                    if self.cfg.browser_headless_mode:
                        self._restart_browser(headless=True)
                        
                sleep(0.5)
                self._clean_page()
                sleep(0.5)
                self._click_enter_game()
                sleep(1)
                self._wait_in_queue(int(self.cfg.cloud_game_max_queue_time) * 60)
                self.confirm_viewport_resolution() # 将浏览器内部分辨率设置为 1920x1080
                
                self.log_info("云游戏启动成功")
                        
                return True 
            except SessionNotCreatedException as e:
                self.log_error(f"浏览器启动失败: {e}")
                self.log_error("请去掉所有浏览器启动参数后重试，如果仍然存在问题，请更换浏览器重试")
                raise
            except Exception as e:
                self.dump_page()
                if attempt == self.MAX_RETRIES:
                    self.log_error("启动云游戏失败，超过最大重试次数。")
                    raise
                self.log_warning(f"启动云游戏失败（正在重试 {attempt + 1}/{self.MAX_RETRIES}）: {e}")
                self._restart_browser(headless=self.cfg.browser_headless_mode)

        return False
    
    def confirm_viewport_resolution(self):
        """
        设置网页分辨率大小
        
        如果云崩铁画面超出浏览器显示范围，页面会反复抽搐，但不影响脚本正常运行
        可以将 cfg.browser_scale_factor 调小来解决这个问题
        """
        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080,
            "deviceScaleFactor": 1,
            "mobile": False
        })
    
    def take_screenshot(self):
        """浏览器内截图，不依赖物理显示"""
        if not self.driver:
            return
        png = self.driver.get_screenshot_as_png()
        return png
    
    def execute_cdp_cmd(self, cmd: str, cmd_args: dict):
        return self.driver.execute_cdp_cmd(cmd, cmd_args)
    
    def get_window_handle(self):
        return self.driver.current_window_handle
    
    def switch_to_game(self) -> bool:
        if self.cfg.browser_headless_mode:
            Logger.warning("当前为无界面模式，无法将游戏切换到前台")
            return False
        else:
            return super().switch_to_game()

    def stop_game(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                return True
            except Exception as e:
                self.log_warning(f"退出浏览器异常: {e}")
            self.driver = None
            return False
        else:
            return True
            
