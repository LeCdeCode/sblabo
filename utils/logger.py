"""Module de logging centralisé et traçage d'erreurs."""
import datetime
import sys


def log(level, message):
    """Affiche un message de log formaté avec timestamp et niveau."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color_codes = {
        "INFO": "\033[94m",      # Bleu
        "SUCCESS": "\033[92m",   # Vert
        "WARN": "\033[93m",      # Jaune
        "ERROR": "\033[91m",     # Rouge
        "DEBUG": "\033[95m"      # Magenta
    }
    reset = "\033[0m"
    color = color_codes.get(level, "")
    print(f"{color}[{now}] [{level}]{reset} {message}")
    sys.stdout.flush()
