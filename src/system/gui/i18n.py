import logging
import os
import subprocess
import sys
import re

from qtpy.QtCore import QTranslator
from qtpy.QtCore import QCoreApplication


def get_lrelease_path():
    """Find lrelease executable automatically"""
    # Check environment variable first
    env_path = os.environ.get("LRELEASE_PATH")
    if env_path and os.path.exists(env_path):
        logging.debug(f"Using lrelease from environment variable: {env_path}")
        return env_path

    # Try to find lrelease or pyside6-lrelease
    lrelease_names = ["lrelease", "pyside6-lrelease"]
    if sys.platform == "win32":
        lrelease_names = ["lrelease.exe", "pyside6-lrelease.exe"]

    for lrelease_name in lrelease_names:
        # Check in Python Scripts directory
        python_scripts = os.path.join(sys.prefix, "Scripts")
        lrelease_path = os.path.join(python_scripts, lrelease_name)
        if os.path.exists(lrelease_path):
            logging.debug(f"Found {lrelease_name} at: {lrelease_path}")
            return lrelease_path

        # Check in system PATH
        try:
            result = subprocess.run(["where" if sys.platform == "win32" else "which", lrelease_name], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip().split("\n")[0]
                logging.debug(f"Found {lrelease_name} in PATH: {path}")
                return path
        except Exception:
            continue

    logging.warning("lrelease not found. Install PySide6 to get pyside6-lrelease.")
    return None


class TranslationManager:
    """
    Translation manager for the elevator control system
    Uses Qt's translation mechanism with .qm files
    """

    def __init__(self, app: QCoreApplication, default_language: str = "中文", lrelease_path: str | None = None):
        """Initialize the translation manager

        Args:
            app: Qt application instance
            default_language: Default language for the interface
            lrelease_path: Custom path to lrelease executable (optional)
        """
        self.app = app
        self.translator = QTranslator()
        self.observers = []
        if lrelease_path is None:
            lrelease_path = get_lrelease_path()
        self.lrelease_path = lrelease_path

        # Map for detected languages (will be populated in scan_available_languages)
        self.language_to_locale = {}

        # Default language (will be updated after scanning)
        self.default_language = default_language
        self.current_language = None

        self.initialize_translations()

    def scan_available_languages(self):
        """Scan translations directory and detect available languages"""
        translations_dir = os.path.join(os.path.dirname(__file__), "translations")

        # Ensure directory exists
        if not os.path.exists(translations_dir):
            logging.warning(f"Translations directory not found: {translations_dir}")
            return

        # Maps for locale codes to language names
        locale_language_map = {
            "zh_CN": "中文",
            "es_ES": "Español",
            "fr_FR": "Français",
            "de_DE": "Deutsch",
            "ja_JP": "日本語",
            "ko_KR": "한국어",
            "ru_RU": "Русский",
            # Add more mappings as needed
        }

        self.language_to_locale = {}
        self.available_languages = []

        # Always include English as available (no translation needed since app is in English)
        self.available_languages.append("English")
        self.language_to_locale["English"] = None  # No locale needed for English

        # Look for .qm files in the translations directory
        pattern = r"elevator_([a-z]{2}_[A-Z]{2})\.qm"
        for filename in os.listdir(translations_dir):
            match = re.match(pattern, filename)
            if match:
                locale_code = match.group(1)
                if locale_code in locale_language_map:
                    language_name = locale_language_map[locale_code]
                    self.language_to_locale[language_name] = locale_code
                    self.available_languages.append(language_name)
                else:
                    # For unknown locales, use the locale code as the language name
                    self.language_to_locale[locale_code] = locale_code
                    self.available_languages.append(locale_code)

        logging.debug(f"Detected available languages: {self.available_languages}")

        if self.default_language not in self.available_languages:
            self.default_language = "English"

        self.set_language(self.default_language)

    def get_current_language(self):
        return self.current_language if self.current_language else self.default_language

    def set_language(self, language):
        """Set the application language"""
        if language not in self.available_languages:
            logging.warning(f"Language '{language}' not available. Using default.")
            language = self.default_language

        if language == self.current_language:
            return

        # Update current language
        self.current_language = language

        # Clear previous translator
        self.app.removeTranslator(self.translator)

        # Get the corresponding locale
        locale_name = self.language_to_locale.get(language)

        # For English, no translation is needed since the app is already in English
        if locale_name is None:
            logging.debug(f"Language '{language}' uses default text (no translation needed)")
            self.notify_observers()
            return

        # Create new translator for non-English languages
        self.translator = QTranslator()

        # Load new translation
        translations_dir = os.path.join(os.path.dirname(__file__), "translations")

        translation_file = f"elevator_{locale_name}"
        if self.translator.load(translation_file, translations_dir):
            self.app.installTranslator(self.translator)
            logging.debug(f"Successfully loaded translation: {translation_file}")
        else:
            logging.warning(f"Failed to load translation file: {translation_file}")
            available_files = os.listdir(translations_dir)
            logging.debug(f"Available files in {translations_dir}: {available_files}")

        # Notify observers
        self.notify_observers()

    def add_observer(self, observer):
        """Add an observer to be notified when language changes"""
        if observer not in self.observers:
            self.observers.append(observer)

    def remove_observer(self, observer):
        """Remove an observer"""
        if observer in self.observers:
            self.observers.remove(observer)

    def notify_observers(self):
        """Notify all observers about language change"""
        for observer in self.observers:
            observer.update_language()

    def initialize_translations(self):
        """Load default language translation if available"""
        # Check and generate .qm files if needed
        self.update_qm_files()

        # Scan for available languages
        self.scan_available_languages()  # Try to load default language
        if self.available_languages:
            self.set_language(self.default_language)
        else:
            logging.warning("No language translations available")

    def update_qm_files(self):
        """Ensure .qm files are up-to-date by generating them from .ts files using lrelease"""
        translations_dir = os.path.join(os.path.dirname(__file__), "translations")

        # Ensure the directory exists
        os.makedirs(translations_dir, exist_ok=True)

        # Check if lrelease is available
        if not self.lrelease_path:
            logging.warning("lrelease not found. Translation files will not be updated automatically.")
            return

        # Process all .ts files in the translations directory
        for filename in os.listdir(translations_dir):
            if filename.endswith(".ts"):
                ts_file = os.path.join(translations_dir, filename)
                qm_file = os.path.join(translations_dir, filename.replace(".ts", ".qm"))  # Check if .qm file needs updating (doesn't exist or older than .ts)
                if not os.path.exists(qm_file) or os.path.getmtime(ts_file) > os.path.getmtime(qm_file):
                    logging.debug(f"Generating {qm_file} from {ts_file}")

                    try:
                        # Run lrelease to generate .qm file
                        result = subprocess.run([self.lrelease_path, ts_file, "-qm", qm_file], capture_output=True, text=True)

                        if result.returncode == 0:
                            logging.debug(f"Successfully generated {qm_file}")
                        else:
                            logging.error(f"Error generating .qm file: {result.stderr}")
                    except Exception as e:
                        logging.error(f"Failed to run lrelease: {str(e)}")
