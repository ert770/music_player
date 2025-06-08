import os
import json
import requests
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from mutagen.mp3 import MP3
import vlc
import random
import threading
import time
import shutil
import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from pydub import AudioSegment
import numpy as np
import pygame
import datetime
from tkinter import simpledialog

MOOD_DIR = "music"
LIKED_SONGS_FILE = "liked_songs.json"
moods = [d for d in os.listdir(MOOD_DIR) if os.path.isdir(os.path.join(MOOD_DIR, d)) and d != "like"]
LIKE_DIR = os.path.join(MOOD_DIR, "like")
if not os.path.exists(LIKE_DIR):
    os.makedirs(LIKE_DIR)
else:
    # 初始化時清空 music/like
    for f in os.listdir(LIKE_DIR):
        if f.endswith('.mp3'):
            os.remove(os.path.join(LIKE_DIR, f))

pygame.mixer.init()

class MusicPlayer:
    def __init__(self, root):
        # 主視窗設定
        self.root = root
        self.root.title("Mood Music Player")
        self.root.geometry("800x500")
        self.root.configure(bg="#181c24")  # 深色背景

        # 設定 ttk 樣式
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#232a36")
        style.configure("TLabel", background="#232a36", foreground="#f8f8f2", font=("Helvetica", 13))
        style.configure("TButton", background="#3a4052", foreground="#f8f8f2", font=("Helvetica", 12), borderwidth=0, focusthickness=3, focuscolor="#6272a4")
        style.map("TButton",
                  background=[("active", "#6272a4"), ("pressed", "#44475a")],
                  foreground=[("active", "#fff")])
        style.configure("TCombobox",
            fieldbackground="#232a36",
            background="#232a36",
            foreground="#f8f8f2",
            font=("Helvetica", 12)
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", "#232a36")],
            foreground=[("readonly", "#f8f8f2")]
        )
        style.configure("Horizontal.TScale", background="#232a36", troughcolor="#44475a", sliderthickness=20)
        style.configure("TProgressbar", background="#6272a4", troughcolor="#44475a", bordercolor="#232a36", lightcolor="#6272a4", darkcolor="#232a36")


        # 判斷現在時間
        now = datetime.datetime.now()
        self.is_day = 6 <= now.hour < 18
        self.bg_paths = {
            "day": "background/bg1_sun.webp",
            "night": "background/bg1_moon.webp"
        }
        self.bg_mode = "day" if self.is_day else "night"
        bg_path = self.bg_paths[self.bg_mode]

        # 載入背景圖片
        try:
            self.original_bg = Image.open(bg_path)
            self.bg_label = tk.Label(self.root)
            self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            self.resize_background(None)
            self.root.bind("<Configure>", self.resize_background)
        except Exception as e:
            print("背景圖片載入失敗:", e)

        # 載入 icon 圖片
        self.icon_images = {}
        try:
            self.icon_images["prev"] = ImageTk.PhotoImage(Image.open("icon/prev.png").resize((40, 40)))
            self.icon_images["play"] = ImageTk.PhotoImage(Image.open("icon/play.png").resize((40, 40)))
            self.icon_images["pause"] = ImageTk.PhotoImage(Image.open("icon/pause.png").resize((40, 40)))
            self.icon_images["next"] = ImageTk.PhotoImage(Image.open("icon/next.png").resize((40, 40)))
            self.icon_images["volume"] = ImageTk.PhotoImage(Image.open("icon/volume.png").resize((20, 20)))
            self.icon_images["like"] = ImageTk.PhotoImage(Image.open("icon/like.png").resize((30, 30)))
            self.icon_images["check"] = ImageTk.PhotoImage(Image.open("icon/check.png").resize((30, 30)))
            self.icon_images["sun"] = ImageTk.PhotoImage(Image.open("icon/sun.png").resize((30, 30)))
            self.icon_images["moon"] = ImageTk.PhotoImage(Image.open("icon/moon1.png").resize((30, 30)))
        except Exception as e:
            print("載入 icon 失敗:", e)

        # 歌單資料夾路徑
        self.playlist_dir = ""
        # 目前歌單檔案名稱列表
        self.playlist = []
        # 目前播放的歌曲索引
        self.current_index = 0
        # 是否暫停
        self.paused = False
        # 目前歌曲長度（秒）
        self.song_length = 100
        # 是否隨機播放（未使用）
        self.shuffle = tk.BooleanVar(value=False)

        # VLC 播放器實例
        self.player = vlc.MediaPlayer()
        # 播放執行緒（未使用）
        self.play_thread = None
        # 監控播放狀態的執行緒
        self.playback_thread = None
        # 監控執行緒是否運作中
        self.playback_thread_running = False

        # 播放模式（0: repeat, 1: shuffle, 2: loop）
        self.play_mode = 2

        # 上方控制列 Frame
        self.top_frame = ttk.Frame(root, style="TFrame")
        self.top_frame.pack(pady=20, fill="x")

        # 心情選單
        ttk.Label(self.top_frame, text="Select Mood:", style="TLabel").grid(row=0, column=0, padx=5)
        self.mood_var = tk.StringVar()
        self.mood_menu = ttk.Combobox(
            self.top_frame,
            textvariable=self.mood_var,
            values=moods + ["❤️ like"],
            state="readonly",
            font=("Helvetica", 12),
            style="TCombobox"
        )
        self.mood_menu.grid(row=0, column=1, padx=5)
        self.mood_menu.bind("<<ComboboxSelected>>", lambda e: self.load_playlist())  # 選擇後自動載入歌單

        # 播放模式按鈕
        self.mode_button = ttk.Button(self.top_frame, text="Mode: loop", command=self.toggle_play_mode, style="TButton")
        self.mode_button.grid(row=0, column=3, padx=10)

        # 日記按鈕
        self.diary_button = ttk.Button(self.top_frame, text="Diary", command=self.open_diary, style="TButton")
        self.diary_button.grid(row=0, column=4, padx=10)

        # 底部控制列 Frame
        self.bottom_bar = tk.Frame(root, bg="#222", height=120)
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

        first_row = tk.Frame(self.bottom_bar, bg="#222", height=60)
        first_row.pack(fill=tk.X, pady=5)
        first_row.pack_propagate(False)

        # 使用 grid 分為三欄
        first_row.columnconfigure(0, weight=1, uniform="group")
        first_row.columnconfigure(1, weight=1, uniform="group")
        first_row.columnconfigure(2, weight=1, uniform="group")

        # 左邊：歌曲資訊與 like
        info_like_frame = tk.Frame(first_row, bg="#222")
        info_like_frame.grid(row=0, column=0, sticky="ew", padx=10)  # sticky="ew"
        self.info_canvas = tk.Canvas(info_like_frame, width=120, height=30, bg="#222", highlightthickness=0)  # width 調小
        self.info_canvas.pack(side=tk.LEFT, fill="x", expand=True)
        self.song_text = self.info_canvas.create_text(0, 15, text="No song loaded", anchor="w", fill="white", font=("Helvetica", 12))
        self.like_button = tk.Button(info_like_frame, image=self.icon_images["like"], command=self.toggle_like, bg="#444", bd=0, activebackground="#333")
        self.like_button.pack(side=tk.LEFT, padx=10)

        # 中間：播放控制（真正置中）
        center_frame = tk.Frame(first_row, bg="#222")
        center_frame.grid(row=0, column=1, sticky="nsew")
        button_style = {"bd": 0, "bg": "#232a36", "activebackground": "#44475a"}
        button_group = tk.Frame(center_frame, bg="#222")
        button_group.pack(expand=True, fill="none")  # 讓按鈕群在 center_frame 置中

        # 讓按鈕群在 button_group 內水平垂直都置中
        inner_frame = tk.Frame(button_group, bg="#222")
        inner_frame.pack(expand=True)
        self.prev_button = tk.Button(inner_frame, image=self.icon_images["prev"], command=self.prev_song, **button_style)
        self.play_button = tk.Button(inner_frame, image=self.icon_images["play"], command=self.toggle_play, **button_style)
        self.next_button = tk.Button(inner_frame, image=self.icon_images["next"], command=self.next_song, **button_style)
        self.prev_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.play_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.next_button.pack(side=tk.LEFT, padx=10, pady=5)
        inner_frame.pack(anchor="center")

        # 右邊：音量
        volume_frame = tk.Frame(first_row, bg="#222")
        volume_frame.grid(row=0, column=2, sticky="ew", padx=10)  # sticky="ew"
        self.volume_label = tk.Label(volume_frame, image=self.icon_images["volume"], bg="#222")
        self.volume_label.pack(side=tk.RIGHT, padx=(0, 5))
        self.volume_slider = ttk.Scale(volume_frame, from_=0.0, to=1.0, value=0.5, command=self.change_volume, length=100)
        self.volume_slider.pack(side=tk.RIGHT)

        # 第二行：時間標籤
        self.progress_time_label = tk.Label(self.bottom_bar, text="00:00 / 00:00", fg="white", bg="#222", font=("Helvetica", 10))
        self.progress_time_label.pack(pady=2)

        # 第三行：進度條
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Scale(self.bottom_bar, from_=0, to=100, variable=self.progress_var, orient="horizontal", length=600, command=self.seek_audio)
        self.progress_bar.pack(pady=2)

        # 右側 Frame（預留）
        self.right_frame = tk.Frame(self.bottom_bar, bg="#222")
        self.right_frame.place(relx=1.0, x=-10, rely=0.5, anchor="e")

        # 啟動進度條更新與快捷鍵綁定
        self.update_progress()
        self.bind_keys()

        # 載入音效
        try:
            self.click_sound = pygame.mixer.Sound("sound/poka01.mp3")
        except Exception as e:
            print("音效載入失敗:", e)
            self.click_sound = None
        weather_mood = self.get_weather_mood()
        if weather_mood in moods:
            self.mood_var.set(weather_mood)
            self.load_playlist()

        # 日夜切換開關
        switch_w, switch_h = 60, 30
        self.theme_canvas = tk.Canvas(volume_frame, width=switch_w, height=switch_h, bg="#222", highlightthickness=0)
        self.theme_canvas.pack(side=tk.RIGHT, padx=(5, 10))

        # 圓角背景（黃/藍色）
        self.theme_bg = self.theme_canvas.create_oval(0, 0, switch_w, switch_h, fill="#f1c40f", outline="#f1c40f")
        self.theme_icon = self.theme_canvas.create_image(15, switch_h // 2, image=self.sun_img)
        self.theme_toggle = self.theme_canvas.create_oval(switch_w - 28, 4, switch_w - 4, switch_h - 4, fill="white", outline="white")

        def toggle_theme(event=None):
            self.bg_mode = "night" if self.bg_mode == "day" else "day"
            new_path = self.bg_paths[self.bg_mode]

            try:
                width = self.root.winfo_width()
                height = self.root.winfo_height()
                new_bg = Image.open(new_path).resize((width, height))
                old_bg = self.original_bg.resize((width, height))

                for alpha in range(0, 11):
                    blend = Image.blend(old_bg, new_bg, alpha / 10.0)
                    tk_image = ImageTk.PhotoImage(blend)
                    self.bg_label.config(image=tk_image)
                    self.bg_label.image = tk_image
                    self.root.update()
                    self.root.after(30)

                # 更新背景與主圖
                self.original_bg = Image.open(new_path)
                self.resize_background(None)

                # 更新開關狀態（icon、顏色、滑球位置）
                if self.bg_mode == "day":
                    self.theme_canvas.itemconfig(self.theme_bg, fill="#f1c40f", outline="#f1c40f")
                    self.theme_canvas.itemconfig(self.theme_icon, image=self.icon_images["sun"])
                    self.theme_canvas.coords(self.theme_toggle, switch_w - 28, 4, switch_w - 4, switch_h - 4)
                else:
                    self.theme_canvas.itemconfig(self.theme_bg, fill="#2c3e50", outline="#2c3e50")
                    self.theme_canvas.itemconfig(self.theme_icon, image=self.icon_images["moon"])
                    self.theme_canvas.coords(self.theme_toggle, 4, 4, 28, switch_h - 4)

            except Exception as e:
                print("切換背景失敗:", e)

        self.theme_canvas.bind("<Button-1>", toggle_theme)

    def get_weather_mood(self):
        try:
            api_key = "88c287ed5607b4cd53491cb52842eb5f"
            city = "Taichung"
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&lang=zh_tw"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            weather = data["weather"][0]["main"].lower()
            # 根據天氣對應 mood
            if "rain" in weather:
                return "chill"
            elif "clear" in weather:
                return "happy"
            elif "cloud" in weather:
                return "relax"
            else:
                return moods[0] if moods else ""
        except Exception as e:
            print("天氣 API 失敗:", e)
            return moods[0] if moods else ""

    def load_liked_songs(self):
        """載入已按讚歌曲清單（從檔案）"""
        if os.path.exists(LIKED_SONGS_FILE):
            with open(LIKED_SONGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_liked_songs(self):
        """儲存已按讚歌曲清單到檔案"""
        with open(LIKED_SONGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.liked_songs, f, ensure_ascii=False, indent=2)

    def update_like_button(self, index):
        """根據目前歌曲是否已按讚，更新 like 按鈕圖示"""
        song = self.playlist[index]
        like_path = os.path.join(LIKE_DIR, song)
        icon = self.icon_images["check"] if os.path.exists(like_path) else self.icon_images["like"]
        self.like_button.config(image=icon)

    def toggle_like(self):
        """切換目前歌曲的按讚狀態"""
        if not self.playlist:
            return
        current_song = self.playlist[self.current_index]
        song_path = os.path.join(self.playlist_dir, current_song)
        like_path = os.path.join(LIKE_DIR, current_song)
        if os.path.exists(like_path):
            os.remove(like_path)
        else:
            if os.path.exists(song_path):
                shutil.copy2(song_path, like_path)
        self.update_like_button(self.current_index)

    def load_playlist(self):
        """根據選擇的心情載入歌單"""
        mood = self.mood_var.get()
        if not mood:
            messagebox.showwarning("Warning", "Please select a mood.")
            return
        if mood == "❤️ like":
            self.playlist_dir = LIKE_DIR
            if not os.path.exists(self.playlist_dir):
                os.makedirs(self.playlist_dir)
            files = [f for f in os.listdir(self.playlist_dir) if f.endswith('.mp3')]
            # 只加入真的存在的檔案
            self.playlist = [f for f in files if os.path.isfile(os.path.join(self.playlist_dir, f))]
        else:
            self.playlist_dir = os.path.join(MOOD_DIR, mood)
            if not os.path.exists(self.playlist_dir):
                os.makedirs(self.playlist_dir)
            files = [f for f in os.listdir(self.playlist_dir) if f.endswith('.mp3')]
            self.playlist = [f for f in files if os.path.isfile(os.path.join(self.playlist_dir, f))]
        if not self.playlist:
            messagebox.showwarning("Warning", "No mp3 files found.")
            return
        if self.play_mode == 1:  # shuffle
            random.shuffle(self.playlist)
        else:
            self.playlist.sort()
        self.current_index = 0
        self.start_playback(self.current_index)

    def resize_background(self, event):
        """根據視窗大小調整背景圖片"""
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        resized = self.original_bg.resize((width, height), Image.Resampling.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(resized)
        self.bg_label.config(image=self.bg_photo)
        self.bg_label.image = self.bg_photo

    def start_playback(self, index):
        """開始播放指定索引的歌曲，並啟動監控執行緒"""
        self.current_index = index
        self.play_song(index)
        if not self.playback_thread or not self.playback_thread.is_alive():
            self.playback_thread_running = True
            self.playback_thread = threading.Thread(target=self.playback_monitor, daemon=True)
            self.playback_thread.start()

    def play_song(self, index):
        """播放指定索引的歌曲"""
        song_path = os.path.join(self.playlist_dir, self.playlist[index])
        try:
            media = vlc.Media(song_path)
            self.player.set_media(media)
            self.player.play()
            self.song_length = MP3(song_path).info.length
            self.root.after(0, self.update_ui_on_play, index)

            threading.Thread(target=self.fade_in, args=(100, 2.0), daemon=True).start()
        except Exception as e:
            print("播放失敗:", e)

    def playback_monitor(self):
        """監控歌曲播放狀態，歌曲結束時自動切換下一首"""
        while self.playback_thread_running:
            time.sleep(1)
            # 如果暫停則跳過
            if self.paused:
                continue
            # 若歌單為空，直接跳過
            if not self.playlist:
                continue
            if self.player.get_state() == vlc.State.Ended:
                self.fade_out(duration=2.0)
                if self.play_mode == 0:  # repeat
                    next_index = self.current_index
                elif self.play_mode == 1:  # shuffle
                    next_index = random.randint(0, len(self.playlist) - 1)
                else:  # loop
                    next_index = (self.current_index + 1) % len(self.playlist)
                self.start_playback(next_index)

    def fade_out(self, duration=2.0):
        """音量淡出效果"""
        current_volume = self.player.audio_get_volume()
        steps = 10
        for i in range(steps):
            volume = int(current_volume * (1 - (i + 1) / steps))
            self.player.audio_set_volume(volume)
            self.root.update()
            time.sleep(duration / steps)

    def fade_in(self, target_volume=100, duration=2.0):
        """音量淡入效果"""
        self.player.audio_set_volume(0)
        self.root.update()
        steps = 10
        for i in range(steps):
            volume = int(target_volume * (i + 1) / steps)
            self.player.audio_set_volume(volume)
            self.root.update()
            time.sleep(duration / steps)

    def update_ui_on_play(self, index):
        """更新 UI 顯示目前播放的歌曲資訊"""
        self.info_canvas.itemconfig(self.song_text, text=f"{self.playlist[index]}")
        self.scroll_position = 0
        self.scroll_direction = 1
        self.play_button.config(image=self.icon_images["pause"])
        self.paused = False
        self.update_like_button(index)

    def play_click_sound(self):
        """播放按鈕音效"""
        if self.click_sound:
            try:
                self.click_sound.play()
            except Exception as e:
                print("音效播放失敗:", e)

    def toggle_play_mode(self):
        """切換播放模式（repeat/shuffle/loop）"""
        self.play_click_sound()
        self.play_mode = (self.play_mode + 1) % 3  # 0: repeat, 1: shuffle, 2: loop
        mode_names = ["repeat", "shuffle", "loop"]
        self.mode_button.config(text=f"Mode: {mode_names[self.play_mode]}")

    def toggle_play(self):
        """播放/暫停切換"""
        self.play_click_sound()
        state = self.player.get_state()
        if state in [vlc.State.Playing, vlc.State.Buffering]:
            self.player.pause()
            self.play_button.config(image=self.icon_images["play"])
            self.paused = True
        elif state in [vlc.State.Paused, vlc.State.Stopped, vlc.State.Ended]:
            self.player.play()
            self.play_button.config(image=self.icon_images["pause"])
            self.paused = False

    def next_song(self):
        """切換到下一首歌"""
        self.play_click_sound()
        if not self.playlist:
            return
        if self.play_mode == 1:  # shuffle
            next_index = random.randint(0, len(self.playlist) - 1)
        elif self.play_mode == 2:  # loop
            next_index = (self.current_index + 1) % len(self.playlist)
        else:  # repeat
            next_index = self.current_index
        self.start_playback(next_index)

    def prev_song(self):
        """切換到上一首歌"""
        self.play_click_sound()
        if not self.playlist:
            return
        if self.play_mode == 1:  # shuffle
            prev_index = random.randint(0, len(self.playlist) - 1)
        elif self.play_mode == 2:  # loop
            prev_index = (self.current_index - 1) % len(self.playlist)
        else:  # repeat
            prev_index = self.current_index
        self.start_playback(prev_index)

    def change_volume(self, val):
        """調整音量"""
        vol = float(val)
        self.player.audio_set_volume(int(vol * 100))

    def seek_audio(self, val):
        """拖曳進度條時跳轉到指定時間"""
        try:
            pos = float(val)
            if self.song_length > 0:
                target_time = int((pos / 100.0) * self.song_length * 1000)
                self.player.set_time(target_time)
        except:
            pass

    def update_progress(self):
        """定時更新進度條與時間標籤"""
        if self.playlist and self.song_length > 0:
            try:
                pos = self.player.get_time() / 1000  # 目前播放秒數
                percent = (pos / self.song_length) * 100
                self.progress_var.set(percent)
                cur_min, cur_sec = divmod(int(pos), 60)
                total_min, total_sec = divmod(int(self.song_length), 60)
                time_str = f"{cur_min:02}:{cur_sec:02} / {total_min:02}:{total_sec:02}"
                self.progress_time_label.config(text=time_str)  # 顯示在進度條上方
            except:
                pass
        self.root.after(500, self.update_progress)

    def scroll_text(self):
        """滾動顯示過長的歌曲名稱"""
        if self.playlist:
            bbox = self.info_canvas.bbox(self.song_text)
            if bbox:
                text_width = bbox[2] - bbox[0]
                if text_width > 250:
                    self.scroll_position += self.scroll_speed * self.scroll_direction
                    if self.scroll_position <= -text_width or self.scroll_position >= 250:
                        self.scroll_direction *= -1
                    self.info_canvas.coords(self.song_text, self.scroll_position, 15)
        self.root.after(100, self.scroll_text)

    def bind_keys(self):
        """綁定快捷鍵（空白鍵播放/暫停、左右切歌、上下調音量）"""
        self.root.bind("<space>", lambda e: self.toggle_play())
        self.root.bind("<Left>", lambda e: self.prev_song())
        self.root.bind("<Right>", lambda e: self.next_song())
        self.root.bind("<Up>", lambda e: self.adjust_volume(0.05))
        self.root.bind("<Down>", lambda e: self.adjust_volume(-0.05))

    def adjust_volume(self, delta):
        """調整音量（快捷鍵用）"""
        cur = self.volume_slider.get()
        new_val = min(max(cur + delta, 0.0), 1.0)
        self.volume_slider.set(new_val)
        self.change_volume(new_val)

    def open_diary(self):
        self.play_click_sound()
        diary_win = tk.Toplevel(self.root)
        diary_win.title("Diary")
        diary_win.geometry("500x500")
        diary_win.configure(bg="white")

        # 使用 grid 布局
        diary_win.rowconfigure(1, weight=1)
        diary_win.columnconfigure(0, weight=1)

        # --- 日期選擇 ---
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        date_var = tk.StringVar(value=today_str)

        date_frame = tk.Frame(diary_win, bg="white")
        date_frame.grid(row=0, column=0, sticky="ew", pady=(10, 0))
        date_frame.columnconfigure(1, weight=1)

        tk.Label(date_frame, text="Date:", font=("Helvetica", 11), bg="white").grid(row=0, column=0, padx=10)
        diary_files = [f[6:-4] for f in os.listdir("diary") if f.startswith("diary_") and f.endswith(".txt")] if os.path.exists("diary") else []
        diary_files = sorted(set(diary_files + [today_str]))
        date_entry = ttk.Combobox(date_frame, textvariable=date_var, font=("Helvetica", 11), width=12, values=diary_files)
        date_entry.grid(row=0, column=1, sticky="w", padx=(0, 10))

        # --- 狀態列 ---
        status_var = tk.StringVar(value="")
        status_label = tk.Label(diary_win, textvariable=status_var, font=("Helvetica", 10), bg="white", fg="green")
        status_label.grid(row=2, column=0, sticky="ew", padx=10)

        # --- 文字區域 ---
        text_area = tk.Text(diary_win, font=("Helvetica", 12), wrap="word", undo=True)
        text_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # --- 字數統計 ---
        count_var = tk.StringVar(value="0 chars")
        count_label = tk.Label(diary_win, textvariable=count_var, font=("Helvetica", 10), bg="white", anchor="e")
        count_label.grid(row=3, column=0, sticky="ew", padx=10)

        # --- 按鈕 ---
        btn_frame = tk.Frame(diary_win, bg="white")
        btn_frame.grid(row=4, column=0, sticky="ew", pady=10, padx=10)
        btn_frame.columnconfigure((0, 1, 2), weight=1, uniform="btns")

        btn_save = tk.Button(btn_frame, text="Save", command=lambda: save_diary(False), font=("Helvetica", 11), height=2)
        btn_clear = tk.Button(btn_frame, text="Clear", command=lambda: clear_diary(), font=("Helvetica", 11), height=2)
        btn_close = tk.Button(btn_frame, text="Close", command=lambda: on_close(), font=("Helvetica", 11), height=2)

        btn_save.grid(row=0, column=0, padx=5, sticky="ew")
        btn_clear.grid(row=0, column=1, padx=5, sticky="ew")
        btn_close.grid(row=0, column=2, padx=5, sticky="ew")

        # --- 變數與功能 ---
        saved_content = [""]

        def get_diary_file():
            diary_dir = "diary"
            os.makedirs(diary_dir, exist_ok=True)
            return os.path.join(diary_dir, f"diary_{date_var.get()}.txt")

        def load_diary():
            file = get_diary_file()
            content = ""
            if os.path.exists(file):
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read()
            text_area.delete("1.0", "end")
            text_area.insert("1.0", content)
            saved_content[0] = content
            update_count()
            status_var.set("")

        def save_diary(close_after=False):
            content = text_area.get("1.0", "end-1c")
            file = get_diary_file()
            with open(file, "w", encoding="utf-8") as f:
                f.write(content)
            saved_content[0] = content
            status_var.set("Saved")
            diary_win.after(3000, lambda: status_var.set(""))
            if close_after:
                diary_win.destroy()

        def on_close():
            content = text_area.get("1.0", "end-1c")
            if content != saved_content[0]:
                if messagebox.askyesno("Unsaved changes", "Content has changed. Save before closing?"):
                    save_diary(close_after=True)
                else:
                    diary_win.destroy()
            else:
                diary_win.destroy()

        def clear_diary():
            text_area.delete("1.0", "end")
            update_count()

        def update_count(event=None):
            content = text_area.get("1.0", "end-1c")
            count_var.set(f"{len(content)} chars")

        def save_shortcut(event=None):
            save_diary()
            return "break"

        # 綁定事件
        date_entry.bind("<<ComboboxSelected>>", lambda e: load_diary())
        date_entry.bind("<Return>", lambda e: load_diary())
        text_area.bind("<<Modified>>", lambda e: (update_count(), text_area.edit_modified(False)))
        text_area.bind("<KeyRelease>", update_count)
        diary_win.bind("<Control-s>", save_shortcut)
        diary_win.protocol("WM_DELETE_WINDOW", on_close)

        # 預設載入
        load_diary()



if __name__ == "__main__":
    root = tk.Tk()
    app = MusicPlayer(root)
    root.mainloop()
