"""
設定檔管理器 - 管理多組設定檔切換
"""
import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class ProfileManager:
    """設定檔管理器"""

    MAX_PROFILES = 20
    MAX_NAME_LENGTH = 10
    DEFAULT_PROFILE = "預設"

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.parent / "config" / "profiles"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 索引檔案路徑
        self.index_file = self.base_dir / "profiles.json"

        # 確保索引存在
        self._ensure_index()

    def _ensure_index(self):
        """確保索引檔案存在，首次執行時建立預設的 5 組設定檔"""
        if not self.index_file.exists():
            # 預設的 5 組設定檔
            default_profiles = [
                {"name": self.DEFAULT_PROFILE, "description": "預設設定檔"},
                {"name": "帳號2", "description": "第二組帳號設定"},
                {"name": "帳號3", "description": "第三組帳號設定"},
                {"name": "工作用", "description": "工作環境設定"},
                {"name": "備用", "description": "備用設定檔"},
            ]

            default_index = {
                "current": self.DEFAULT_PROFILE,
                "profiles": {}
            }

            # 建立所有預設設定檔
            for profile in default_profiles:
                default_index["profiles"][profile["name"]] = {
                    "created_at": datetime.now().isoformat(),
                    "description": profile["description"]
                }

            self._save_index(default_index)

            # 如果有舊的 config.yaml，複製為預設設定檔
            old_config = self.base_dir.parent / "config.yaml"
            if old_config.exists():
                shutil.copy2(old_config, self._get_profile_path(self.DEFAULT_PROFILE))
            else:
                # 為預設設定檔建立空白設定
                self._create_default_config(self._get_profile_path(self.DEFAULT_PROFILE))

            # 為其他設定檔建立空白設定
            for profile in default_profiles[1:]:
                profile_path = self._get_profile_path(profile["name"])
                if not profile_path.exists():
                    self._create_default_config(profile_path)

    def _load_index(self) -> dict:
        """載入索引"""
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"current": self.DEFAULT_PROFILE, "profiles": {}}

    def _save_index(self, index: dict):
        """儲存索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _get_profile_path(self, name: str) -> Path:
        """取得設定檔路徑"""
        # 用安全的檔名
        safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-', ' '))
        return self.base_dir / f"{safe_name}.yaml"

    def _get_cookie_path(self, name: str) -> Path:
        """取得設定檔對應的 Cookie 路徑"""
        safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-', ' '))
        return self.base_dir / f"{safe_name}_cookies.json"

    def get_profile_list(self) -> List[Dict]:
        """取得所有設定檔列表"""
        index = self._load_index()
        profiles = []
        for name, info in index.get("profiles", {}).items():
            profiles.append({
                "name": name,
                "created_at": info.get("created_at", ""),
                "description": info.get("description", ""),
                "is_current": name == index.get("current")
            })
        return sorted(profiles, key=lambda x: x["name"])

    def get_current_profile(self) -> str:
        """取得目前使用的設定檔名稱"""
        index = self._load_index()
        return index.get("current", self.DEFAULT_PROFILE)

    def set_current_profile(self, name: str) -> bool:
        """設定目前使用的設定檔"""
        index = self._load_index()
        if name not in index.get("profiles", {}):
            return False

        index["current"] = name
        self._save_index(index)
        return True

    def get_profile_config_path(self, name: str = None) -> Path:
        """取得設定檔的 config.yaml 路徑"""
        if name is None:
            name = self.get_current_profile()
        return self._get_profile_path(name)

    def get_profile_cookie_path(self, name: str = None) -> Path:
        """取得設定檔的 Cookie 路徑"""
        if name is None:
            name = self.get_current_profile()
        return self._get_cookie_path(name)

    def create_profile(self, name: str, description: str = "",
                       copy_from: str = None) -> bool:
        """建立新設定檔"""
        # 驗證名稱
        name = name.strip()
        if not name:
            return False
        if len(name) > self.MAX_NAME_LENGTH:
            return False

        index = self._load_index()

        # 檢查數量限制
        if len(index.get("profiles", {})) >= self.MAX_PROFILES:
            return False

        # 檢查是否已存在
        if name in index.get("profiles", {}):
            return False

        # 建立設定檔
        profile_path = self._get_profile_path(name)

        if copy_from and copy_from in index.get("profiles", {}):
            # 從現有設定檔複製
            source_path = self._get_profile_path(copy_from)
            if source_path.exists():
                shutil.copy2(source_path, profile_path)

            # 複製 Cookie
            source_cookie = self._get_cookie_path(copy_from)
            if source_cookie.exists():
                shutil.copy2(source_cookie, self._get_cookie_path(name))
        else:
            # 建立空的設定檔
            self._create_default_config(profile_path)

        # 更新索引
        if "profiles" not in index:
            index["profiles"] = {}

        index["profiles"][name] = {
            "created_at": datetime.now().isoformat(),
            "description": description
        }
        self._save_index(index)

        return True

    def _create_default_config(self, path: Path):
        """建立預設設定檔"""
        import yaml

        default_config = {
            "forum": {
                "base_url": "https://fastzone.org",
                "target_sections": [
                    {"name": "成人短片專用區", "fid": "77"},
                    {"name": "AV 成人無碼區", "fid": "74"},
                    {"name": "AV 西方交流區", "fid": "170"}
                ],
                "title_filters": [
                    "@mg", "@ mg", "mg@", "mg @",
                    "mega@", "mega @", "@mega", "@ mega",
                    "gofile@", "gofile @", "@gofile", "@ gofile",
                    "@send", "@ send", "send@", "send @",
                    "mf@", "mf @", "@mf", "@ mf"
                ],
                "web_download_keywords": [
                    "@gd", "gd@", "@ gd", "gd @",
                    "transfer@", "@transfer", "transfer @", "@ transfer"
                ],
                "smg_keywords": [
                    "@smg", "@ smg", "smg@", "smg @"
                ]
            },
            "auth": {
                "cookie_file": str(self._get_cookie_path(path.stem))
            },
            "paths": {
                "download_dir": "c:\\dl\\dl\\",
                "extract_dir": "c:\\dl\\rar\\",
                "winrar_path": ""
            },
            "jdownloader": {
                "exe_path": "",
                "folderwatch_path": "",
                "auto_start": True
            },
            "smg": {
                "exe_path": "",
                "download_dir": ""
            },
            "scraper": {
                "pages_per_section": 1,
                "posts_per_section": 15,
                "delay_between_requests": 2,
                "delay_between_thanks": 5,
                "max_file_size_mb": 2048
            },
            "extract_interval": 60,
            "database": {
                "retention_days": 30
            }
        }

        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """重新命名設定檔"""
        new_name = new_name.strip()
        if not new_name or len(new_name) > self.MAX_NAME_LENGTH:
            return False

        index = self._load_index()

        if old_name not in index.get("profiles", {}):
            return False
        if new_name in index.get("profiles", {}):
            return False

        # 重新命名檔案
        old_path = self._get_profile_path(old_name)
        new_path = self._get_profile_path(new_name)

        if old_path.exists():
            shutil.move(old_path, new_path)

        # 重新命名 Cookie
        old_cookie = self._get_cookie_path(old_name)
        new_cookie = self._get_cookie_path(new_name)

        if old_cookie.exists():
            shutil.move(old_cookie, new_cookie)

        # 更新索引
        info = index["profiles"].pop(old_name)
        index["profiles"][new_name] = info

        if index.get("current") == old_name:
            index["current"] = new_name

        self._save_index(index)
        return True

    def delete_profile(self, name: str) -> bool:
        """刪除設定檔"""
        index = self._load_index()

        if name not in index.get("profiles", {}):
            return False

        # 不能刪除最後一個設定檔
        if len(index.get("profiles", {})) <= 1:
            return False

        # 刪除檔案
        profile_path = self._get_profile_path(name)
        if profile_path.exists():
            profile_path.unlink()

        cookie_path = self._get_cookie_path(name)
        if cookie_path.exists():
            cookie_path.unlink()

        # 更新索引
        del index["profiles"][name]

        # 如果刪除的是目前設定檔，切換到第一個
        if index.get("current") == name:
            index["current"] = list(index["profiles"].keys())[0]

        self._save_index(index)
        return True

    def update_description(self, name: str, description: str) -> bool:
        """更新設定檔描述"""
        index = self._load_index()

        if name not in index.get("profiles", {}):
            return False

        index["profiles"][name]["description"] = description
        self._save_index(index)
        return True

    def export_profile(self, name: str, export_path: str) -> bool:
        """匯出設定檔"""
        index = self._load_index()

        if name not in index.get("profiles", {}):
            return False

        export_dir = Path(export_path)
        export_dir.mkdir(parents=True, exist_ok=True)

        # 複製設定檔
        profile_path = self._get_profile_path(name)
        if profile_path.exists():
            shutil.copy2(profile_path, export_dir / f"{name}.yaml")

        # 複製 Cookie
        cookie_path = self._get_cookie_path(name)
        if cookie_path.exists():
            shutil.copy2(cookie_path, export_dir / f"{name}_cookies.json")

        return True

    def import_profile(self, import_path: str, name: str = None) -> bool:
        """匯入設定檔"""
        import_file = Path(import_path)

        if not import_file.exists():
            return False

        # 決定名稱
        if name is None:
            name = import_file.stem
            if name.endswith("_cookies"):
                name = name[:-8]

        name = name[:self.MAX_NAME_LENGTH]

        index = self._load_index()

        # 檢查數量限制
        if name not in index.get("profiles", {}) and \
           len(index.get("profiles", {})) >= self.MAX_PROFILES:
            return False

        # 複製檔案
        if import_file.suffix == '.yaml':
            shutil.copy2(import_file, self._get_profile_path(name))
        elif import_file.suffix == '.json':
            shutil.copy2(import_file, self._get_cookie_path(name))

        # 更新索引
        if "profiles" not in index:
            index["profiles"] = {}

        if name not in index["profiles"]:
            index["profiles"][name] = {
                "created_at": datetime.now().isoformat(),
                "description": "匯入的設定檔"
            }
            self._save_index(index)

        return True
