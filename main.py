import os
import json
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
        style.configure("TCombobox", fieldbackground="#232a36", background="#232a36", foreground="#f8f8f2", font=("Helvetica", 12))
        style.configure("Horizontal.TScale", background="#232a36", troughcolor="#44475a", sliderthickness=20)
        style.configure("TProgressbar", background="#6272a4", troughcolor="#44475a", bordercolor="#232a36", lightcolor="#6272a4", darkcolor="#232a36")

        # 載入背景圖片
        try:
            self.original_bg = Image.open("background/moon.jpg")
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

        # 第一行：歌曲資訊、like 按鈕、播放控制、音量
        first_row = tk.Frame(self.bottom_bar, bg="#222")
        first_row.pack(fill=tk.X, pady=5)

        # 歌曲資訊顯示區
        self.info_canvas = tk.Canvas(first_row, width=250, height=30, bg="#222", highlightthickness=0)
        self.info_canvas.pack(side=tk.LEFT, padx=10)
        self.song_text = self.info_canvas.create_text(0, 15, text="No song loaded", anchor="w", fill="white", font=("Helvetica", 12))

        # 喜好按鈕
        self.like_button = tk.Button(first_row, image=self.icon_images["like"], command=self.toggle_like, bg="#444", bd=0, activebackground="#333")
        self.like_button.pack(side=tk.LEFT, padx=10)

        # 播放控制按鈕區
        center_frame = tk.Frame(first_row, bg="#222")
        center_frame.pack(side=tk.LEFT, padx=850)  # 增加 padx 讓它往左移

        button_style = {"bd": 0, "bg": "#232a36", "activebackground": "#44475a"}
        self.prev_button = tk.Button(center_frame, image=self.icon_images["prev"], command=self.prev_song, **button_style)
        self.play_button = tk.Button(center_frame, image=self.icon_images["play"], command=self.toggle_play, **button_style)
        self.next_button = tk.Button(center_frame, image=self.icon_images["next"], command=self.next_song, **button_style)
        self.prev_button.pack(side=tk.LEFT, padx=10)
        self.play_button.pack(side=tk.LEFT, padx=10)
        self.next_button.pack(side=tk.LEFT, padx=10)

        # 音量滑桿與圖示（icon 在左，滑桿在右）
        self.volume_label = tk.Label(first_row, image=self.icon_images["volume"], bg="#222") # 音量圖示
        self.volume_label.pack(side=tk.LEFT, padx=(5, 0))
        self.volume_slider = ttk.Scale(first_row, from_=0.0, to=1.0, value=0.5, command=self.change_volume, length=100)
        self.volume_slider.pack(side=tk.LEFT, padx=(0, 5))

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
                if self.play_mode == 0:  # repeat
                    next_index = self.current_index
                elif self.play_mode == 1:  # shuffle
                    next_index = random.randint(0, len(self.playlist) - 1)
                else:  # loop
                    next_index = (self.current_index + 1) % len(self.playlist)
                self.start_playback(next_index)

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
        """Open diary window with auto-save, date selection, change detection, word count, shortcuts, and friendly UI (all text in English)"""
        self.play_click_sound()
        diary_win = tk.Toplevel(self.root)
        diary_win.title("Diary")
        diary_win.geometry("500x500")
        diary_win.configure(bg="white")

        # Date selection
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        date_var = tk.StringVar(value=today_str)
        tk.Label(diary_win, text="Date:", font=("Helvetica", 11), bg="white").pack(pady=(10, 0))
        date_entry = ttk.Combobox(diary_win, textvariable=date_var, font=("Helvetica", 11), width=12)
        diary_files = [f[6:-4] for f in os.listdir() if f.startswith("diary_") and f.endswith(".txt")]
        diary_files = sorted(set(diary_files + [today_str]))
        date_entry['values'] = diary_files
        date_entry.pack(pady=(0, 5))

        # Status bar
        status_var = tk.StringVar(value="")
        status_label = tk.Label(diary_win, textvariable=status_var, font=("Helvetica", 10), bg="white", fg="green")
        status_label.pack(pady=(0, 2))

        # Text area
        text_area = tk.Text(diary_win, font=("Helvetica", 12), wrap="word", undo=True)
        text_area.pack(expand=True, fill="both", padx=10, pady=5)

        # Word count
        count_var = tk.StringVar(value="0 chars")
        count_label = tk.Label(diary_win, textvariable=count_var, font=("Helvetica", 10), bg="white", anchor="e")
        count_label.pack(fill="x", padx=10)

        # Change detection
        saved_content = [""]

        def get_diary_file():
            return f"diary_{date_var.get()}.txt"

        def load_diary():
            """Load diary content by date"""
            file = get_diary_file()
            if os.path.exists(file):
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                content = ""
            text_area.delete("1.0", "end")
            text_area.insert("1.0", content)
            saved_content[0] = content
            update_count()
            status_var.set("")

        def save_diary(close_after=False):
            """Save diary content to file"""
            content = text_area.get("1.0", "end-1c")
            file = get_diary_file()
            with open(file, "w", encoding="utf-8") as f:
                f.write(content)
            saved_content[0] = content
            status_var.set("Saved")
            # 3秒後自動清除提示
            diary_win.after(3000, lambda: status_var.set(""))
            if close_after:
                diary_win.destroy()

        def on_close():
            """Auto-save or prompt on close if changed"""
            content = text_area.get("1.0", "end-1c")
            if content != saved_content[0]:
                if messagebox.askyesno("Unsaved changes", "Content has changed. Save before closing?"):
                    save_diary(close_after=True)
                else:
                    diary_win.destroy()
            else:
                diary_win.destroy()

        def clear_diary():
            """Clear content"""
            text_area.delete("1.0", "end")
            update_count()

        def update_count(event=None):
            """Update word/char count"""
            content = text_area.get("1.0", "end-1c")
            count_var.set(f"{len(content)} chars")

        def save_shortcut(event=None):
            save_diary()
            return "break"

        # 日期切換時自動載入
        date_entry.bind("<<ComboboxSelected>>", lambda e: load_diary())
        date_entry.bind("<Return>", lambda e: load_diary())

        # 內容變更時更新字數
        text_area.bind("<<Modified>>", lambda e: (update_count(), text_area.edit_modified(False)))
        text_area.bind("<KeyRelease>", update_count)

        # Ctrl+S 快捷鍵儲存
        diary_win.bind("<Control-s>", save_shortcut)

        # UI按鈕
        btn_frame = tk.Frame(diary_win, bg="white")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Save (Ctrl+S)", command=save_diary, font=("Helvetica", 11)).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Clear", command=clear_diary, font=("Helvetica", 11)).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Close", command=on_close, font=("Helvetica", 11)).pack(side="left", padx=5)

        # 關閉視窗時自動儲存或提醒
        diary_win.protocol("WM_DELETE_WINDOW", on_close)

        # 預設載入今天的日記
        load_diary()

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicPlayer(root)
    root.mainloop()
