import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import re
import csv
import sys
import platform
from pathlib import Path
from datetime import datetime
import os
import queue
from itertools import product
import tempfile
import shutil
import random
import json
from collections import defaultdict, Counter

# 第三方库依赖
import undetected_chromedriver as uc
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException, NoSuchWindowException
from selenium.webdriver.common.action_chains import ActionChains
import subprocess
import socket

# ==================== 工具函数 ====================
def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except:
            return True

def start_chrome_debug_mode(port=9222):
    """启动Chrome调试模式（使用与bat脚本相同的参数）
    
    Returns:
        bool: 是否成功启动或已在运行
    """
    # 检查端口是否已被占用
    if is_port_in_use(port):
        return True  # 已有浏览器在该端口运行
    
    # 根据操作系统启动Chrome
    try:
        if platform.system() == 'Windows':
            # 使用与bat脚本完全相同的参数
            user_data_dir = os.path.join(os.environ.get('TEMP', 'C:\\Temp'), 'chrome_debug_kkday')
            
            # 确保目录存在
            if not os.path.exists(user_data_dir):
                os.makedirs(user_data_dir)
            
            # 启动Chrome（使用start命令，与bat脚本一致）
            # start chrome.exe --remote-debugging-port=9222 --user-data-dir="%USER_DATA_DIR%"
            subprocess.Popen(
                f'start chrome.exe --remote-debugging-port={port} --user-data-dir="{user_data_dir}"',
                shell=True
            )
            
        elif platform.system() == 'Darwin':  # macOS
            user_data_dir = os.path.expanduser('~/.chrome_debug_kkday')
            
            if not os.path.exists(user_data_dir):
                os.makedirs(user_data_dir)
            
            chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
            
            subprocess.Popen([
                chrome_path,
                f'--remote-debugging-port={port}',
                f'--user-data-dir={user_data_dir}'
            ])
            
        elif platform.system() == 'Linux':
            user_data_dir = os.path.expanduser('~/.chrome_debug_kkday')
            
            if not os.path.exists(user_data_dir):
                os.makedirs(user_data_dir)
            
            subprocess.Popen([
                'google-chrome',
                f'--remote-debugging-port={port}',
                f'--user-data-dir={user_data_dir}'
            ])
        
        # 等待浏览器启动
        time.sleep(2)
        return is_port_in_use(port)
        
    except Exception as e:
        print(f"启动Chrome失败: {e}")
        return False

# ==================== KKday反爬虫对抗模块 ====================
class KKdayAntiDetectionHelper:
    """KKday反爬虫检测辅助类 - 连接到已启动的普通浏览器"""
    
    def __init__(self, driver):
        self.driver = driver
    
    def inject_stealth_scripts(self):
        """注入增强版隐身脚本（KKday专用）"""
        stealth_js = """
        // ========== 核心WebDriver特征隐藏 ==========
        
        // 1. 覆盖navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // 2. 删除自动化标识
        delete navigator.__proto__.webdriver;
        
        // 3. 覆盖Chrome自动化标识
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // ========== Permissions API ==========
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // ========== Plugins & MimeTypes ==========
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const pluginArray = [
                    {
                        name: 'Chrome PDF Plugin',
                        filename: 'internal-pdf-viewer',
                        description: 'Portable Document Format',
                        length: 1
                    },
                    {
                        name: 'Chrome PDF Viewer',
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                        description: '',
                        length: 1
                    },
                    {
                        name: 'Native Client',
                        filename: 'internal-nacl-plugin',
                        description: '',
                        length: 2
                    }
                ];
                pluginArray.item = function(index) { return this[index]; };
                pluginArray.namedItem = function(name) {
                    return this.find(p => p.name === name);
                };
                return pluginArray;
            }
        });
        
        // ========== 语言设置 ==========
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en']
        });
        
        // ========== 硬件并发数 ==========
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        // ========== 设备内存 ==========
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
        
        console.log('🔒 KKday Stealth mode activated');
        """
        
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': stealth_js
            })
        except Exception as e:
            print(f"注入脚本失败: {e}")
    
    def random_delay(self, min_ms=50, max_ms=150):
        """随机延迟（毫秒）- 快速版本"""
        delay = random.uniform(min_ms, max_ms) / 1000.0
        time.sleep(delay)
    
    def simulate_human_mouse_move(self, element):
        """模拟人类鼠标移动"""
        try:
            actions = ActionChains(self.driver)
            # 先移动到元素附近
            actions.move_to_element_with_offset(element, 
                                                random.randint(-5, 5), 
                                                random.randint(-5, 5))
            actions.pause(random.uniform(0.1, 0.3))
            # 再移动到元素中心
            actions.move_to_element(element)
            actions.pause(random.uniform(0.05, 0.15))
            actions.perform()
            time.sleep(random.uniform(0.05, 0.15))
        except:
            pass


class KKdayScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("KKday商品SKU价格提取工具")
        self.root.geometry("900x750")

        # --- Instance Variables ---
        self.driver = None
        self.scraping_thread = None
        self.is_paused = threading.Event()
        self.is_stopped = threading.Event()
        self.step_generator = None
        self.urls_to_process = []
        self.is_paused.set()
        
        # SKU层级跟踪
        self.max_sku_layers = 0
        
        # 结果缓存 - 存储所有抓取的数据
        self.all_results = []  # 累积所有结果
        self.combinations_result = []
        self.combination_count = 0
        self.failed_options = []
        
        # 反检测助手
        self.anti_detection = None
        
        # 构建GUI
        self._build_gui()
    
    def _build_gui(self):
        """构建GUI界面"""
        # 顶部控制区
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)
        
        # URL输入
        ttk.Label(control_frame, text="KKday商品URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(control_frame, width=70)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.url_entry.insert(0, "https://www.kkday.com/...")
        
        # 调试端口输入
        ttk.Label(control_frame, text="浏览器调试端口:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.port_entry = ttk.Entry(control_frame, width=20)
        self.port_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.port_entry.insert(0, "9222")
        
        # 按钮区 - 参考Klook布局
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=10)
        
        self.btn_connect = ttk.Button(button_frame, text="连接浏览器", command=self.connect_browser)
        self.btn_connect.grid(row=0, column=0, padx=5)
        
        self.btn_prev_tab = ttk.Button(button_frame, text="◀ 前一标签", command=self.switch_to_prev_tab, state=tk.DISABLED)
        self.btn_prev_tab.grid(row=0, column=1, padx=5)
        
        self.btn_next_tab = ttk.Button(button_frame, text="后一标签 ▶", command=self.switch_to_next_tab, state=tk.DISABLED)
        self.btn_next_tab.grid(row=0, column=2, padx=5)
        
        self.btn_start = ttk.Button(button_frame, text="开始抓取", command=self.start_scraping, state=tk.DISABLED)
        self.btn_start.grid(row=0, column=3, padx=5)
        
        self.btn_pause = ttk.Button(button_frame, text="暂停", command=self.pause_scraping, state=tk.DISABLED)
        self.btn_pause.grid(row=0, column=4, padx=5)
        
        self.btn_stop = ttk.Button(button_frame, text="停止", command=self.stop_scraping, state=tk.DISABLED)
        self.btn_stop.grid(row=0, column=5, padx=5)
        
        self.btn_save = ttk.Button(button_frame, text="手动保存", command=self.manual_save, state=tk.DISABLED)
        self.btn_save.grid(row=0, column=6, padx=5)
        
        self.btn_close = ttk.Button(button_frame, text="断开浏览器", command=self.close_browser)
        self.btn_close.grid(row=0, column=7, padx=5)
        
        # 日志区
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=25, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 状态栏
        self.status_label = ttk.Label(self.root, text="未连接", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
    
    def log(self, message):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def connect_browser(self):
        """连接到浏览器 - 自动启动或连接现有浏览器"""
        try:
            port = int(self.port_entry.get().strip() or "9222")
            
            self.log(f"检查端口 {port} 状态...")
            
            # 检查端口是否已被占用
            if is_port_in_use(port):
                self.log(f"✓ 检测到端口 {port} 已有浏览器运行")
            else:
                self.log(f"端口 {port} 未被占用，正在启动Chrome...")
                if start_chrome_debug_mode(port):
                    self.log("✓ Chrome调试模式已启动")
                else:
                    raise Exception("无法启动Chrome浏览器，请手动启动或检查Chrome是否已安装")
            
            # 连接到浏览器
            self.log(f"正在连接到端口 {port}...")
            
            # 使用标准Selenium连接到已存在的浏览器（不启动新浏览器）
            options = ChromeOptions()
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            
            # 禁用所有可能导致启动新浏览器的选项
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            
            self.log("尝试连接现有浏览器实例...")
            
            # 尝试连接（带重试）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        self.log(f"重试连接 ({attempt + 1}/{max_retries})...")
                        time.sleep(1)
                    
                    # 使用标准webdriver连接（不会启动新浏览器）
                    self.driver = webdriver.Chrome(options=options)
                    self.log("✓ 已建立WebDriver连接")
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    self.log(f"连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    continue
            
            # 验证连接并获取当前标签
            try:
                handles = self.driver.window_handles
                self.log(f"✓ 浏览器共有 {len(handles)} 个标签页")
                
                if handles:
                    current_url = self.driver.current_url
                    self.log(f"✓ 当前页面: {current_url}")
            except Exception as e:
                self.log(f"⚠ 获取浏览器状态警告: {e}")
            
            # 初始化反检测助手
            self.anti_detection = KKdayAntiDetectionHelper(self.driver)
            self.anti_detection.inject_stealth_scripts()
            
            self.log("✅ 成功连接到浏览器")
            self.log("💡 请在浏览器中打开KKday商品页面，或使用前后标签按钮切换")
            
            self.status_label.config(text="已连接")
            self.btn_start.config(state=tk.NORMAL)
            self.btn_save.config(state=tk.NORMAL)
            self.btn_prev_tab.config(state=tk.NORMAL)
            self.btn_next_tab.config(state=tk.NORMAL)
            self.btn_connect.config(state=tk.DISABLED)
            
        except Exception as e:
            self.log(f"❌ 连接失败: {e}")
            error_msg = f"无法连接到浏览器:\n{e}\n\n"
            error_msg += "可能的原因:\n"
            error_msg += "1. Chrome浏览器未安装或不在PATH中\n"
            error_msg += "2. 端口被其他程序占用\n"
            error_msg += f"3. 防火墙阻止了端口 {port}\n"
            messagebox.showerror("连接失败", error_msg)
    
    def switch_to_prev_tab(self):
        """切换到前一个标签页（带窗口检测）"""
        if not self.driver:
            self.log("❌ 请先连接浏览器")
            return
        
        try:
            # 验证driver连接
            if not self._verify_driver_connection():
                return
            
            # 获取所有窗口句柄
            all_handles = self.driver.window_handles
            current_handle = self.driver.current_window_handle
            
            if len(all_handles) == 1:
                self.log("⚠ 只有一个标签页，无法切换")
                return
            
            # 找到当前标签的索引
            current_index = all_handles.index(current_handle)
            
            # 计算前一个标签的索引（循环）
            prev_index = (current_index - 1) % len(all_handles)
            
            # 切换到前一个标签
            self.driver.switch_to.window(all_handles[prev_index])
            time.sleep(0.15)
            
            # 获取新标签页信息
            new_url = self.driver.current_url
            new_title = self.driver.title
            
            self.log(f"◀ 切换到前一标签 ({current_index + 1} → {prev_index + 1}/{len(all_handles)})")
            self.log(f"📄 {new_title[:50]}")
            self.log(f"🔗 {new_url}")
            
            # 更新URL输入框
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, new_url)
            
        except NoSuchWindowException:
            self.log("❌ 窗口已关闭，请尝试重新连接")
            self._prompt_reconnect()
        except Exception as e:
            self.log(f"❌ 切换失败: {e}")
            if "target window already closed" in str(e).lower():
                self._prompt_reconnect()
    
    def switch_to_next_tab(self):
        """切换到后一个标签页（带窗口检测）"""
        if not self.driver:
            self.log("❌ 请先连接浏览器")
            return
        
        try:
            # 验证driver连接
            if not self._verify_driver_connection():
                return
            
            # 获取所有窗口句柄
            all_handles = self.driver.window_handles
            current_handle = self.driver.current_window_handle
            
            if len(all_handles) == 1:
                self.log("⚠ 只有一个标签页，无法切换")
                return
            
            # 找到当前标签的索引
            current_index = all_handles.index(current_handle)
            
            # 计算后一个标签的索引（循环）
            next_index = (current_index + 1) % len(all_handles)
            
            # 切换到后一个标签
            self.driver.switch_to.window(all_handles[next_index])
            time.sleep(0.15)
            
            # 获取新标签页信息
            new_url = self.driver.current_url
            new_title = self.driver.title
            
            self.log(f"▶ 切换到后一标签 ({current_index + 1} → {next_index + 1}/{len(all_handles)})")
            self.log(f"📄 {new_title[:50]}")
            self.log(f"🔗 {new_url}")
            
            # 更新URL输入框
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, new_url)
            
        except NoSuchWindowException:
            self.log("❌ 窗口已关闭，请尝试重新连接")
            self._prompt_reconnect()
        except Exception as e:
            self.log(f"❌ 切换失败: {e}")
            if "target window already closed" in str(e).lower():
                self._prompt_reconnect()
    
    def _verify_driver_connection(self):
        """验证driver连接是否有效
        
        Returns:
            bool: 连接是否有效
        """
        try:
            # 尝试获取窗口句柄
            handles = self.driver.window_handles
            if not handles:
                self.log("⚠ 没有可用的窗口")
                self._prompt_reconnect()
                return False
            
            # 尝试获取当前窗口
            try:
                current = self.driver.current_window_handle
                if current not in handles:
                    # 当前窗口已关闭，切换到第一个可用窗口
                    self.log("⚠ 当前窗口已关闭，切换到第一个可用窗口")
                    self.driver.switch_to.window(handles[0])
            except NoSuchWindowException:
                # 当前窗口不存在，切换到第一个
                self.log("⚠ 当前窗口不存在，切换到第一个窗口")
                self.driver.switch_to.window(handles[0])
            
            return True
            
        except NoSuchWindowException:
            self.log("❌ 所有窗口都已关闭")
            self._prompt_reconnect()
            return False
        except Exception as e:
            self.log(f"❌ 验证连接失败: {e}")
            self._prompt_reconnect()
            return False
    
    def _prompt_reconnect(self):
        """提示用户重新连接"""
        self.log("💡 建议：点击'断开浏览器'然后重新点击'连接浏览器'")
        response = messagebox.askyesno(
            "连接异常", 
            "浏览器连接出现异常，是否自动重新连接？\n\n"
            "（建议先在浏览器中打开目标页面）"
        )
        if response:
            self.close_browser()
            time.sleep(0.5)
            self.connect_browser()
    
    def start_scraping(self):
        """开始抓取 - 连续模式，不自动结束"""
        if not self.driver:
            messagebox.showerror("错误", "请先连接浏览器")
            return
        
        url = self.url_entry.get().strip()
        if not url or url == "https://www.kkday.com/...":
            # 使用当前浏览器页面的URL
            url = self.driver.current_url
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, url)
        
        if "kkday.com" not in url:
            messagebox.showerror("错误", "请输入有效的KKday商品URL")
            return
        
        self.urls_to_process = [url]
        self.is_stopped.clear()
        self.is_paused.set()
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_save.config(state=tk.NORMAL)
        
        # 启动抓取线程
        self.scraping_thread = threading.Thread(target=self._scraping_worker, daemon=True)
        self.scraping_thread.start()
    
    def pause_scraping(self):
        """暂停/继续抓取"""
        if self.is_paused.is_set():
            self.is_paused.clear()
            self.btn_pause.config(text="继续")
            self.log("⏸️ 已暂停")
        else:
            self.is_paused.set()
            self.btn_pause.config(text="暂停")
            self.log("▶️ 继续运行")
    
    def stop_scraping(self):
        """停止抓取"""
        self.is_stopped.set()
        self.log("🛑 正在停止...")
        self.btn_stop.config(state=tk.DISABLED)
    
    def manual_save(self):
        """手动保存当前累积的结果"""
        if not self.all_results:
            messagebox.showwarning("提示", "当前没有可保存的数据")
            return
        
        self.log(f"手动保存 {len(self.all_results)} 条数据...")
        self._save_to_xlsx(self.all_results)
    
    def close_browser(self):
        """断开浏览器连接"""
        if self.scraping_thread and self.scraping_thread.is_alive():
            messagebox.showwarning("提示", "请先停止抓取任务")
            return
        
        if self.driver:
            try:
                self.log("正在断开浏览器连接...")
                self.driver.quit()
                self.driver = None
                self.anti_detection = None
                self.log("✅ 已断开连接")
                
                self.status_label.config(text="未连接")
                self.btn_connect.config(state=tk.NORMAL)
                self.btn_start.config(state=tk.DISABLED)
                self.btn_pause.config(state=tk.DISABLED)
                self.btn_stop.config(state=tk.DISABLED)
                self.btn_save.config(state=tk.DISABLED)
                self.btn_prev_tab.config(state=tk.DISABLED)
                self.btn_next_tab.config(state=tk.DISABLED)
            except Exception as e:
                self.log(f"断开连接时出错: {e}")
        else:
            self.log("浏览器尚未连接")
    
    def _scraping_worker(self):
        """抓取工作线程 - 连续模式"""
        try:
            for url in self.urls_to_process:
                if self.is_stopped.is_set():
                    break
                
                self.log(f"\n{'='*60}")
                self.log(f"开始处理: {url}")
                self.log(f"{'='*60}")
                
                # 导航到URL - 快速
                if self.driver.current_url != url:
                    self.driver.get(url)
                    time.sleep(1)  # 减少页面加载等待
                
                # 抓取数据
                results = self._scrape_single_page(url)
                if results:
                    # 累积到总结果中
                    self.all_results.extend(results)
                    self.log(f"✅ 本次获取 {len(results)} 个SKU组合")
                    self.log(f"📊 累计已获取 {len(self.all_results)} 条数据")
            
            # 连续模式：不自动保存，等待用户手动保存或继续添加URL
            if not self.is_stopped.is_set():
                self.log(f"\n✅ 当前URL处理完成！")
                self.log(f"📊 累计数据: {len(self.all_results)} 条")
                self.log("💡 提示: 可以继续输入新URL抓取，或点击'手动保存'保存数据")
            
        except Exception as e:
            self.log(f"❌ 抓取失败: {e}")
            import traceback
            self.log(traceback.format_exc())
        
        finally:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_pause.config(state=tk.DISABLED, text="暂停")
            self.btn_stop.config(state=tk.DISABLED)
            self.status_label.config(text=f"就绪 (已抓取{len(self.all_results)}条)")
    
    def _scrape_single_page(self, url):
        """抓取单个KKday页面的SKU价格数据 - 支持多个大卡片（方案）"""
        # 重置计数器
        self.max_sku_layers = 0
        all_results = []
        product_id = self._extract_product_id(url)
        
        try:
            # 等待页面加载
            self.log("等待页面加载...")
            time.sleep(1)
            
            # 查找所有大卡片（方案）- 使用更精确的选择器
            self.log("查找商品方案（大卡片）...")
            package_cards = self.driver.find_elements(By.CSS_SELECTOR, "#option-sec > div > div.option-item")
            
            if not package_cards:
                self.log("❌ 未找到任何商品方案")
                return []
            
            self.log(f"✓ 找到 {len(package_cards)} 个商品方案")
            
            # 遍历每个大卡片
            for card_index, card in enumerate(package_cards, 1):
                if self.is_stopped.is_set():
                    break
                
                self.log(f"\n{'='*60}")
                self.log(f"处理方案 {card_index}/{len(package_cards)}")
                self.log(f"{'='*60}")
                
                # 重新获取该卡片元素（避免stale element）
                try:
                    package_cards = self.driver.find_elements(By.CSS_SELECTOR, "#option-sec > div > div.option-item")
                    card = package_cards[card_index - 1]
                except:
                    self.log(f"⚠ 重新获取方案 {card_index} 失败")
                    continue
                
                # 提取大卡片信息（在点击之前）
                package_info = self._extract_package_info(card)
                if not package_info:
                    self.log(f"⚠ 方案 {card_index} 信息提取失败，跳过")
                    continue
                
                self.log(f"📦 方案名称: {package_info['title']}")
                if package_info['description']:
                    desc_preview = package_info['description'][:100]
                    self.log(f"📄 方案描述: {desc_preview}{'...' if len(package_info['description']) > 100 else ''}")
                
                # 点击"选择"按钮展开大卡片的SKU选项
                if not self._click_package_select_button(card):
                    self.log(f"⚠ 无法展开方案 {card_index}，跳过")
                    continue
                
                # 等待SKU区域展开
                time.sleep(0.3)
                
                # 重新获取元素（因为DOM可能更新）
                try:
                    package_cards = self.driver.find_elements(By.CSS_SELECTOR, "#option-sec > div > div.option-item")
                    card = package_cards[card_index - 1]
                except:
                    self.log(f"⚠ SKU展开后重新获取方案 {card_index} 失败")
                    continue
                
                # 提取该大卡片下的所有SKU组合
                self.combinations_result = []
                self.combination_count = 0
                sku_combinations = self._extract_package_sku_prices(card)
                
                if not sku_combinations:
                    self.log(f"⚠ 方案 {card_index} 未找到SKU组合")
                    # 即使没有SKU组合，也继续下一个方案（不点"取消选择"）
                    continue
                
                # 构建结果 - 包含大卡片信息
                for index, sku_combo in enumerate(sku_combinations):
                    result = {
                        '商品ID': product_id if card_index == 1 and index == 0 else '',
                        '网址': url if card_index == 1 and index == 0 else '',
                        '方案名称': package_info['title'] if index == 0 else '',
                        '方案描述': package_info['description'] if index == 0 else ''
                    }
                    
                    # 解析价格
                    currency, price = self._parse_price(sku_combo.get('price', 'N/A'))
                    
                    # 拆分SKU组合到各列
                    sku_parts = sku_combo.get('combination', '').split(' | ')
                    for i in range(self.max_sku_layers):
                        if i < len(sku_parts):
                            result[f'SKU层级{i+1}'] = sku_parts[i]
                        else:
                            result[f'SKU层级{i+1}'] = ''
                    
                    result.update({
                        '货币': currency,
                        '价格': price
                    })
                    
                    all_results.append(result)
                
                self.log(f"✅ 方案 {card_index} 完成，获取 {len(sku_combinations)} 个组合")
                self.log(f"💡 自动进入下一个方案（不点'取消选择'）")
                
                # 不点击"取消选择"，直接进入下一个循环
            
            self.log(f"\n{'='*60}")
            self.log(f"页面抓取完成！共 {len(all_results)} 条数据")
            self.log(f"{'='*60}")
            
            return all_results
            
        except Exception as e:
            self.log(f"❌ 页面抓取失败: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []
    
    def _extract_package_info(self, card_element):
        """提取大卡片（方案）信息
        
        Args:
            card_element: 大卡片的WebElement
            
        Returns:
            dict: {'title': 方案名称, 'description': 方案描述}
        """
        try:
            # 提取方案标题
            # 选择器: h3.package-span-list > span.kk-u-text-h6
            title_elem = card_element.find_element(By.CSS_SELECTOR, "h3.package-span-list > span.kk-u-text-h6")
            title = title_elem.text.strip()
            
            # 提取方案描述 - 需要处理随机ID
            # 完整路径示例: #optionItem1836947 > div.option-head > div > div.flex > div > div.package-desc > ul
            # 简化选择器，不依赖ID: div.option-head div.package-desc ul
            description_parts = []
            try:
                # 使用不依赖随机ID的选择器
                desc_container = card_element.find_element(By.CSS_SELECTOR, "div.option-head div.package-desc ul")
                desc_lis = desc_container.find_elements(By.TAG_NAME, "li")
                
                for li in desc_lis:
                    text = li.text.strip()
                    if text:
                        description_parts.append(text)
            except Exception as e:
                self.log(f"提取方案描述失败: {e}")
            
            description = ' | '.join(description_parts) if description_parts else ''
            
            return {
                'title': title,
                'description': description
            }
            
        except Exception as e:
            self.log(f"提取方案信息失败: {e}")
            return None
    
    def _click_package_select_button(self, card_element):
        """点击大卡片的"选择"按钮以展开SKU选项
        
        逻辑：
        - 只点击"选择"按钮（不是"取消選擇"）
        - 如果已经是"取消選擇"状态，说明已展开，直接返回成功
        - 如果没有按钮（单一方案），检查是否已有"selected"类，直接返回成功
        - 点击后等待SKU区域展开
        
        Args:
            card_element: 大卡片的WebElement
            
        Returns:
            bool: 是否成功点击或已展开
        """
        try:
            # 检查大卡片是否已有"selected"类（单一方案的情况）
            card_class = card_element.get_attribute('class') or ''
            if 'selected' in card_class:
                self.log("✓ 方案已自动展开（单一方案，无需按钮）")
                return True
            
            # 尝试查找"选择"按钮
            try:
                select_btn = card_element.find_element(By.CSS_SELECTOR, "button.select-option")
            except NoSuchElementException:
                # 没有找到按钮，检查SKU区域是否已可见
                self.log("⚠ 未找到'选择'按钮")
                try:
                    booking = card_element.find_element(By.CSS_SELECTOR, "div.option-booking")
                    if booking.is_displayed():
                        self.log("✓ SKU区域已可见（无需按钮）")
                        return True
                    else:
                        self.log("❌ SKU区域不可见且无按钮")
                        return False
                except:
                    self.log("❌ 既无按钮也无SKU区域")
                    return False
            
            # 找到按钮，检查按钮文本
            btn_text = select_btn.text.strip()
            
            if "取消" in btn_text or btn_text == "取消選擇":
                # 已经展开（按钮显示"取消選擇"），无需点击
                self.log("✓ 方案已展开（按钮显示'取消選擇'）")
                return True
            
            if "選擇" not in btn_text and "选择" not in btn_text:
                self.log(f"⚠ 未识别的按钮文本: {btn_text}")
                return False
            
            # 滚动到按钮
            self._scroll_to_element(select_btn)
            time.sleep(0.05)
            
            # 点击"选择"按钮
            self.driver.execute_script("arguments[0].click();", select_btn)
            self.log(f"✓ 点击'选择'按钮 (原文本: {btn_text})")
            
            # 等待按钮状态变化（变为"取消選擇"）
            time.sleep(0.2)
            
            # 验证是否成功展开
            try:
                new_text = select_btn.text.strip()
                if "取消" in new_text:
                    self.log(f"✓ 方案已展开（按钮变为'{new_text}'）")
                    return True
                else:
                    self.log(f"⚠ 按钮文本未变化: {new_text}")
                    return True  # 仍然尝试继续
            except:
                return True  # 忽略验证错误
            
        except Exception as e:
            self.log(f"处理选择按钮时出错: {e}")
            # 尝试检查SKU区域是否仍然可见
            try:
                booking = card_element.find_element(By.CSS_SELECTOR, "div.option-booking")
                if booking.is_displayed():
                    self.log("✓ 虽有错误但SKU区域可见，继续")
                    return True
            except:
                pass
            return False
    
    def _extract_package_sku_prices(self, card_element):
        """提取单个大卡片下的所有SKU组合和价格
        
        Args:
            card_element: 大卡片的WebElement
            
        Returns:
            list: SKU组合列表
        """
        try:
            # 查找该卡片下展开的SKU容器
            # 选择器: div.option-booking (在当前card下)
            sku_booking = card_element.find_element(By.CSS_SELECTOR, "div.option-booking")
            
            # 检查是否可见
            if not sku_booking.is_displayed():
                self.log("SKU选项区域未展开")
                return []
            
            # 获取SKU层级
            sku_layers = self._get_all_sku_layers_kkday(sku_booking)
            if not sku_layers:
                self.log("未找到SKU层级")
                return []
            
            self.log(f"检测到 {len(sku_layers)} 个SKU层")
            self.max_sku_layers = max(self.max_sku_layers, len(sku_layers))
            
            # 使用DFS遍历所有SKU组合
            self.combinations_result = []
            self._dfs_traverse_kkday(sku_layers, 0, [])
            
            return self.combinations_result
            
        except Exception as e:
            self.log(f"提取方案SKU失败: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []
    
    def _extract_all_sku_prices(self):
        """提取所有SKU组合和对应价格 - KKday版本"""
        self.log("🚀 开始KKday SKU遍历...")
        
        try:
            # 快速等待SKU容器加载
            self.log("等待SKU选项加载...")
            time.sleep(0.5)  # 减少初始等待时间
            
            # 查找SKU容器 - KKday结构
            # 基础选择器: #option-sec > div > div > div.option-booking > div > div.item > div.row > div:nth-child(2)
            try:
                # 简化选择器
                sku_container = self.driver.find_element(By.CSS_SELECTOR, "#option-sec div.option-booking")
                self.log("✓ 找到SKU容器")
            except:
                self.log("❌ 未找到SKU容器")
                return []
            
            # 滚动到SKU容器 - 快速
            self._scroll_to_element(sku_container)
            time.sleep(0.05)  # 极短等待
            
            # 获取所有SKU层级
            sku_layers = self._get_all_sku_layers_kkday(sku_container)
            if not sku_layers:
                self.log("未找到SKU层级")
                return []
            
            self.log(f"检测到 {len(sku_layers)} 个SKU层")
            self.max_sku_layers = len(sku_layers)
            
            # 深度优先遍历所有组合
            self._dfs_traverse_kkday(sku_layers, 0, [])
            
            self.log(f"✅ 遍历完成，共 {len(self.combinations_result)} 个组合")
            return self.combinations_result
            
        except Exception as e:
            self.log(f"SKU提取异常: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []
    
    def _get_all_sku_layers_kkday(self, container):
        """获取所有SKU层级 - KKday结构（增强版）
        
        支持多种结构：
        1. div.row > div:nth-child(2) > div:nth-child(N) > div.form-group
        2. div.col-md-6 > div.form-group (直接结构)
        3. 通用: div.form-group
        """
        try:
            result_layers = []
            layer_containers = []
            
            # 方法1: 尝试标准结构 div.row > div:nth-child(2) > div:nth-child(N)
            try:
                row_container = container.find_element(By.CSS_SELECTOR, "div.item > div.row")
                self.log("✓ 找到标准div.row结构")
                
                for nth in range(1, 10):  # 最多支持9层
                    try:
                        selector = f"div.row > div:nth-child(2) > div:nth-child({nth})"
                        layer_div = row_container.find_element(By.CSS_SELECTOR, selector)
                        
                        # 检查是否包含form-group
                        form_groups = layer_div.find_elements(By.CSS_SELECTOR, "div.form-group")
                        if form_groups:
                            layer_containers.extend(form_groups)
                    except:
                        if nth > 3:  # 前3层都找不到就停止
                            break
                        continue
            except:
                self.log("⚠ 未找到标准div.row结构，尝试备用方案")
            
            # 方法2: 尝试 div.col-md-6 直接结构
            if not layer_containers:
                try:
                    col_containers = container.find_elements(By.CSS_SELECTOR, "div.col-md-6")
                    for col in col_containers:
                        form_groups = col.find_elements(By.CSS_SELECTOR, "div.form-group")
                        if form_groups:
                            layer_containers.extend(form_groups)
                            self.log(f"✓ 从div.col-md-6找到 {len(form_groups)} 个层级")
                except:
                    pass
            
            # 方法3: 通用选择器（最后的备用方案）
            if not layer_containers:
                layer_containers = container.find_elements(By.CSS_SELECTOR, "div.form-group")
                if layer_containers:
                    self.log(f"✓ 使用通用选择器找到 {len(layer_containers)} 个层级")
            
            if not layer_containers:
                self.log("❌ 未找到任何form-group层级")
                return []
            
            self.log(f"总共找到 {len(layer_containers)} 个form-group")
            
            # 解析每个层级
            for idx, layer in enumerate(layer_containers):
                try:
                    # 检查是否可见
                    if not layer.is_displayed():
                        self.log(f"  层级 {idx+1}: 不可见，跳过")
                        continue
                    
                    # 获取层级标题
                    title = "未命名层级"
                    try:
                        # 尝试多种标题选择器
                        title_selectors = [
                            "span.kk-u-text-body-md",
                            "span.kk-u-text-darker",
                            "label",
                            "span"
                        ]
                        for selector in title_selectors:
                            try:
                                title_elem = layer.find_element(By.CSS_SELECTOR, selector)
                                title_text = title_elem.text.strip()
                                if title_text and len(title_text) < 100:  # 合理长度的标题
                                    title = title_text
                                    break
                            except:
                                continue
                    except:
                        pass
                    
                    # 获取该层的所有按钮
                    buttons = layer.find_elements(By.CSS_SELECTOR, "button.spec-btn")
                    
                    if not buttons:
                        self.log(f"  层级 {idx+1}: {title} - 没有按钮，跳过")
                        continue
                    
                    # 统计可用和不可用的按钮
                    available_count = 0
                    disabled_count = 0
                    selected_count = 0
                    
                    for btn in buttons:
                        is_disabled = btn.get_attribute('disabled') is not None
                        btn_class = btn.get_attribute('class') or ''
                        
                        if is_disabled or 'disabled' in btn_class:
                            disabled_count += 1
                        else:
                            available_count += 1
                        
                        if 'selected' in btn_class:
                            selected_count += 1
                    
                    # 特殊处理：只有一个选项且已选中
                    if len(buttons) == 1 and selected_count == 1:
                        self.log(f"  层级 {idx+1}: {title} - 1个选项已默认选中，自动跳过")
                        # 将此层标记为"自动选中"，DFS时会自动处理
                    
                    self.log(f"  层级 {idx+1}: {title} - {len(buttons)}个选项 (可用:{available_count}, 禁用:{disabled_count}, 已选:{selected_count})")
                    
                    result_layers.append({
                        'index': idx,
                        'title': title,
                        'element': layer,
                        'buttons': buttons,
                        'auto_selected': (len(buttons) == 1 and selected_count == 1)  # 标记是否自动选中
                    })
                    
                except Exception as e:
                    self.log(f"⚠ 解析层级 {idx+1} 失败: {e}")
                    continue
            
            return result_layers
            
        except Exception as e:
            self.log(f"❌ 获取SKU层级失败: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []
    
    def _dfs_traverse_kkday(self, sku_layers, current_layer_idx, selected_path):
        """深度优先遍历KKday SKU树（高速优化版）
        
        优化要点：
        1. 减少所有time.sleep延迟
        2. 增加元素稳定性检测
        3. 智能刷新策略
        """
        # 停止检查
        if self.is_stopped.is_set():
            return
        
        # 暂停检查
        while not self.is_paused.is_set():
            time.sleep(0.1)
        
        # 到达最后一层，获取价格
        if current_layer_idx >= len(sku_layers):
            price = self._get_current_price_kkday()
            if price and price not in ['价格未找到', '价格获取失败']:
                combination = {
                    'combination': ' | '.join(selected_path),
                    'price': price
                }
                self.combinations_result.append(combination)
                self.combination_count += 1
                if self.combination_count % 5 == 0:  # 减少日志频率
                    self.log(f"  已获取 {self.combination_count} 个组合...")
            return
        
        # 获取当前层
        current_layer = sku_layers[current_layer_idx]
        
        # 实时获取可用选项
        available_options = self._get_available_options_kkday(current_layer)
        
        if not available_options:
            return
        
        if current_layer_idx == 0:  # 只在第一层显示详细信息
            self.log(f"📍 第{current_layer_idx+1}层 [{current_layer['title']}]: {len(available_options)} 个可用选项")
        
        # 遍历当前层的每个可用选项
        for opt_idx, option in enumerate(available_options):
            if self.is_stopped.is_set():
                return
            
            # 检查是否为自动选中的选项
            if option.get('auto_selected', False):
                selected_path.append(option['text'])
                self._dfs_traverse_kkday(sku_layers, current_layer_idx + 1, selected_path)
                selected_path.pop()
                continue
            
            # 【优化1】快速点击，无验证延迟
            if not self._click_option_safe_kkday(option):
                continue
            
            # 【优化2】极短验证（20ms）
            time.sleep(0.02)
            
            # 【优化3】快速验证选中状态
            try:
                if 'selected' not in (option['element'].get_attribute('class') or ''):
                    continue
            except:
                pass
            
            # 添加到路径
            selected_path.append(option['text'])
            
            # 【优化4】智能刷新策略
            if current_layer_idx + 1 < len(sku_layers):
                # 【关键优化】减少等待时间：150ms → 80ms
                time.sleep(0.08)
                
                # 【优化5】带重试的刷新机制
                try:
                    refreshed_layers = self._refresh_sku_layers_with_retry(current_layer_idx)
                    if refreshed_layers:
                        sku_layers = sku_layers[:current_layer_idx+1] + refreshed_layers[current_layer_idx+1:]
                except Exception as e:
                    pass  # 刷新失败继续用旧层级
            
            # 递归到下一层
            self._dfs_traverse_kkday(sku_layers, current_layer_idx + 1, selected_path)
            
            # 回溯
            selected_path.pop()
            
            # 【优化6】最后一个选项才取消选中
            if opt_idx == len(available_options) - 1:
                try:
                    if 'selected' in (option['element'].get_attribute('class') or ''):
                        option['element'].click()
                        time.sleep(0.02)  # 减少取消选中延迟：50ms → 20ms
                except:
                    pass
            
            # 【优化7】极短回溯延迟（10ms → 5ms）
            time.sleep(0.005)
    
    def _refresh_sku_layers_with_retry(self, current_layer_idx, max_retries=2):
        """带重试的层级刷新（增强稳健性）
        
        Args:
            current_layer_idx: 当前层索引
            max_retries: 最大重试次数
            
        Returns:
            list: 刷新后的层级列表，失败返回None
        """
        for attempt in range(max_retries):
            try:
                sku_container = self.driver.find_element(By.CSS_SELECTOR, "#option-sec div.option-booking")
                
                # 【稳健性】验证容器是否有效
                if not sku_container.is_displayed():
                    if attempt < max_retries - 1:
                        time.sleep(0.05)
                        continue
                    return None
                
                refreshed_layers = self._get_all_sku_layers_kkday(sku_container)
                
                # 【稳健性】验证层级数量
                if refreshed_layers and len(refreshed_layers) > current_layer_idx + 1:
                    return refreshed_layers
                
                if attempt < max_retries - 1:
                    time.sleep(0.05)
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.05)
                else:
                    return None
        
        return None
    
    def _get_available_options_kkday(self, layer):
        """获取KKday层级的可用选项（增强版）
        
        特殊处理：
        - 如果层级只有1个选项且已选中，返回该选项（标记为auto_selected）
        - 这种情况下不需要点击，DFS会直接使用
        """
        try:
            # 检查是否为自动选中的层级
            if layer.get('auto_selected', False):
                # 返回唯一的已选中选项
                btn = layer['buttons'][0]
                text = btn.text.strip()
                if text:
                    return [{
                        'element': btn,
                        'text': text,
                        'auto_selected': True  # 标记为自动选中
                    }]
                return []
            
            # 正常情况：查找所有可用选项
            buttons = layer['element'].find_elements(By.CSS_SELECTOR, "button.spec-btn")
            available = []
            
            for btn in buttons:
                try:
                    # 检查是否disabled
                    is_disabled = btn.get_attribute('disabled') is not None
                    class_name = btn.get_attribute('class') or ''
                    has_disabled_class = 'disabled' in class_name
                    
                    # 检查是否可见
                    is_visible = btn.is_displayed()
                    
                    if not is_disabled and not has_disabled_class and is_visible:
                        text = btn.text.strip()
                        if text:
                            available.append({
                                'element': btn,
                                'text': text,
                                'auto_selected': False
                            })
                except:
                    continue
            
            return available
            
        except Exception as e:
            self.log(f"获取可用选项失败: {e}")
            return []
    
    def _click_option_safe_kkday(self, option):
        """安全点击KKday选项（高速优化版）"""
        try:
            element = option['element']
            
            # 【稳健性1】验证元素有效性
            try:
                if not element.is_displayed() or not element.is_enabled():
                    return False
            except:
                return False
            
            # 【优化】直接JS点击，移除滚动延迟
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except:
                # 备用方案：普通点击
                try:
                    element.click()
                    return True
                except:
                    return False
                    
        except Exception as e:
            return False
    
    def _get_current_price_kkday(self):
        """获取当前选择的价格 - KKday版本
        
        根据用户提供的HTML结构：
        价格位置: #option-sec > div > div > div.option-booking > div > div.item > 
                 div.layout-flex-row.layout-flex-row--vertical-align-center.layout-flex-row--gap-4.layout-flex-row--no-left > 
                 div.layout-flex-row__remain > div > div.prod-booking-section.kk-u-text-dark > div > div > div
        """
        try:
            # 等待价格更新 - 快速等待，参考trip: 200ms
            time.sleep(0.15)
            
            # 使用用户提供的精确选择器
            price_selectors = [
                # 主选择器（用户提供的完整路径）
                "#option-sec div.option-booking div.item div.layout-flex-row--no-left div.layout-flex-row__remain div.prod-booking-section div",
                # 简化版本1
                "div.prod-booking-section.kk-u-text-dark div div div",
                # 简化版本2
                "div.layout-flex-row__remain div.prod-booking-section",
                # 备用选择器
                "div.prod-booking-section span[class*='price']",
                "div.prod-booking-section div[class*='price']",
                "div.option-booking div[class*='TWD']",
                "div.option-booking span[class*='TWD']",
                # 通用价格选择器
                "div[class*='booking'] span",
                "div[class*='booking'] div"
            ]
            
            # 尝试每个选择器
            for selector_idx, selector in enumerate(price_selectors):
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for elem in elements:
                        if not elem.is_displayed():
                            continue
                        
                        price_text = elem.text.strip()
                        
                        # 验证价格格式（KKday主要使用TWD，格式如: TWD 1,234 或 1,234）
                        if price_text:
                            # 检查是否包含数字和可能的逗号
                            if re.search(r'[\d,]+', price_text):
                                # 排除纯文字（如"立即預訂"等）
                                if not re.search(r'^[^\d]+$', price_text):
                                    # 提取包含数字的部分
                                    price_match = re.search(r'(TWD\s*)?[\d,]+(\.\d+)?', price_text)
                                    if price_match:
                                        self.log(f"✓ 找到价格: {price_text} (选择器 #{selector_idx+1})")
                                        return price_text
                except Exception as e:
                    continue
            
            # 如果所有选择器都失败，尝试智能搜索（仅重试最后一次）
            if retry == max_retries - 1:
                self.log("⚠ 主选择器未找到价格，尝试智能搜索...")
                try:
                    # 查找所有包含"TWD"或数字的可见文本
                    all_elements = self.driver.find_elements(By.XPATH, 
                        "//*[contains(text(), 'TWD') or contains(text(), '1') or contains(text(), '2') or contains(text(), '3') or contains(text(), '4') or contains(text(), '5')]")
                    
                    for elem in all_elements:
                        if elem.is_displayed():
                            text = elem.text.strip()
                            # 检查是否是价格格式
                            if re.match(r'(TWD\s*)?\d{2,}', text) and '月' not in text and '日' not in text:
                                self.log(f"✓ 智能搜索找到价格: {text}")
                                return text
                except:
                    pass
            else:
                # 快速重试前短暂等待
                time.sleep(0.1)  # 参考trip: 100ms
            
            self.log("❌ 未找到价格")
            return "价格未找到"
            
        except Exception as e:
            self.log(f"获取价格失败: {e}")
            import traceback
            self.log(traceback.format_exc())
            return "价格获取失败"
    
    def _scroll_to_element(self, element):
        """滚动到元素 - 快速滚动"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(0.02)  # 极短等待，参考trip: 20ms
        except:
            pass
    
    def _extract_product_id(self, url):
        """从URL提取商品ID"""
        try:
            # KKday URL格式: https://www.kkday.com/zh-tw/product/xxxxx
            match = re.search(r'/product/(\w+)', url)
            if match:
                return match.group(1)
            return "ID提取失败"
        except:
            return "ID提取失败"
    
    def _parse_price(self, price_text):
        """解析价格文本，分离货币和数值 - 参考Klook实现"""
        if not price_text or price_text in ['N/A', '价格未找到', '价格获取失败']:
            return 'N/A', 'N/A'
        
        try:
            # KKday价格格式: TWD 1,234 或 NT$1,234 或 1,234
            # 先尝试匹配带货币符号的格式
            match = re.match(r'([A-Z]{2,3}|NT)\$?\s?(\d+(?:,\d{3})*(?:\.\d+)?)', price_text)
            if match:
                currency = match.group(1)
                # NT转换为TWD
                if currency == 'NT':
                    currency = 'TWD'
                price_value = match.group(2).replace(',', '')  # 移除千位分隔符
                return currency, price_value
            
            # 如果没有货币符号，尝试提取纯数字
            match_num = re.search(r'(\d+(?:,\d{3})*(?:\.\d+)?)', price_text)
            if match_num:
                price_value = match_num.group(1).replace(',', '')
                # KKday默认使用新台币
                return 'TWD', price_value
            
            # 如果无法解析，返回原始文本
            return price_text, ''
        except Exception:
            return price_text, ''
    
    def _save_to_xlsx(self, data):
        """保存数据到XLSX格式 - 参考Klook实现"""
        if not data:
            self.log("没有数据可保存。")
            return
        
        # 保存到专用文件夹
        downloads_path = Path.home() / "Downloads" / "KKday_scraping"
        downloads_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kkday_price_results_{timestamp}.xlsx"
        filepath = downloads_path / filename
        
        self.log(f"正在将结果保存到: {filepath}")
        
        try:
            # 创建工作簿
            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.title = "KKday商品数据"
            
            # 动态构建列标题 - 方案信息在前，SKU在中间，价格在最后
            fieldnames = ['商品ID', '网址', '方案名称', '方案描述']
            
            # 添加SKU列
            for i in range(self.max_sku_layers):
                fieldnames.append(f'SKU层级{i+1}')
            
            # 添加价格列
            fieldnames.extend(['货币', '价格'])
            
            # 写入标题行
            for col_num, header in enumerate(fieldnames, 1):
                cell = worksheet.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
            
            # 写入数据行
            for row_num, item in enumerate(data, 2):
                for col_num, field in enumerate(fieldnames, 1):
                    value = item.get(field, '')
                    worksheet.cell(row=row_num, column=col_num, value=value)
            
            # 自适应列宽（参考Klook）
            for column in worksheet.columns:
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                
                # 设置列宽，最小为8，最大为80（方案描述可能较长）
                adjusted_width = min(max(max_length + 2, 8), 80)
                worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # 保存文件
            workbook.save(filepath)
            self.log("XLSX文件保存成功！")
            messagebox.showinfo("完成", f"数据已成功保存到：\nDownloads\\KKday_scraping\\\n\n文件名: {filename}\n共保存 {len(data)} 条记录")
            
            # 尝试打开文件夹
            try:
                if platform.system() == 'Windows':
                    os.startfile(downloads_path)
                elif platform.system() == 'Darwin':
                    os.system(f'open "{downloads_path}"')
                else:
                    os.system(f'xdg-open "{downloads_path}"')
            except:
                pass
                
        except Exception as e:
            self.log(f"错误：保存XLSX文件失败: {e}")
            messagebox.showerror("保存失败", f"无法保存XLSX文件。\n\n错误详情: {e}")
    
    def cleanup(self):
        """清理资源"""
        if self.driver:
            try:
                # 不关闭浏览器，只断开连接
                self.driver.quit()
            except:
                pass


def main():
    root = tk.Tk()
    app = KKdayScraperApp(root)
    
    def on_closing():
        if messagebox.askokcancel("退出", "确定要退出吗?"):
            app.cleanup()
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

