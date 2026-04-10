#!/usr/bin/env python3
"""
Skrypt instalacyjny dla Tesla Controller
Automatyzuje proces konfiguracji projektu
"""

import os
import sys
import subprocess
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

console = Console()

def show_welcome():
    """Wyświetla powitanie"""
    welcome_text = """
    🚗 Tesla Controller - Instalacja
    
    Ten skrypt pomoże Ci skonfigurować program do kontrolowania pojazdu Tesla.
    """
    console.print(Panel(welcome_text, title="Witaj!", border_style="green"))

def check_python_version():
    """Sprawdza wersję Pythona"""
    if sys.version_info < (3, 8):
        console.print("[red]Błąd: Wymagany Python 3.8 lub nowszy[/red]")
        console.print(f"[yellow]Aktualna wersja: {sys.version}[/yellow]")
        return False
    
    console.print(f"[green]✓ Python {sys.version_info.major}.{sys.version_info.minor} - OK[/green]")
    return True

def create_virtual_environment():
    """Tworzy środowisko wirtualne"""
    if os.path.exists('venv'):
        if not Confirm.ask("Środowisko wirtualne już istnieje. Czy chcesz je usunąć i utworzyć nowe?"):
            return True
        
        console.print("[yellow]Usuwanie istniejącego środowiska wirtualnego...[/yellow]")
        import shutil
        shutil.rmtree('venv')
    
    console.print("[yellow]Tworzenie środowiska wirtualnego...[/yellow]")
    
    try:
        subprocess.check_call([sys.executable, "-m", "venv", "venv"])
        console.print("[green]✓ Środowisko wirtualne utworzone pomyślnie[/green]")
        return True
    except subprocess.CalledProcessError:
        console.print("[red]✗ Błąd podczas tworzenia środowiska wirtualnego[/red]")
        return False

def get_venv_python():
    """Zwraca ścieżkę do interpretera Python w środowisku wirtualnym"""
    if os.name == 'nt':  # Windows
        return os.path.join('venv', 'Scripts', 'python.exe')
    else:  # macOS/Linux
        return os.path.join('venv', 'bin', 'python')

def install_dependencies():
    """Instaluje zależności w środowisku wirtualnym"""
    console.print("[yellow]Instalowanie zależności w środowisku wirtualnym...[/yellow]")
    
    venv_python = get_venv_python()
    
    try:
        subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([venv_python, "-m", "pip", "install", "-r", "requirements.txt"])
        console.print("[green]✓ Zależności zainstalowane pomyślnie[/green]")
        return True
    except subprocess.CalledProcessError:
        console.print("[red]✗ Błąd podczas instalacji zależności[/red]")
        return False

def create_env_file():
    """Tworzy plik .env z konfiguracją"""
    if os.path.exists('.env'):
        if not Confirm.ask("Plik .env już istnieje. Czy chcesz go nadpisać?"):
            return True
    
    console.print("[yellow]Konfiguracja Tesla API...[/yellow]")
    
    email = Prompt.ask("Podaj adres email konta Tesla")
    
    # Opcjonalne ustawienia
    cache_file = Prompt.ask("Nazwa pliku cache", default="tesla_cache.json")
    timeout = Prompt.ask("Timeout połączenia (sekundy)", default="30")
    
    env_content = f"""# Tesla Controller - Konfiguracja
TESLA_EMAIL={email}
TESLA_CACHE_FILE={cache_file}
TESLA_TIMEOUT={timeout}

# Opcjonalne ustawienia dla Fleet API (jeśli używasz)
# TESLA_CLIENT_ID=your_client_id
# TESLA_CLIENT_SECRET=your_client_secret
# TESLA_DOMAIN=https://off-peak-charge-v2.vercel.app
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        console.print("[green]✓ Plik .env utworzony pomyślnie[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ Błąd podczas tworzenia pliku .env: {e}[/red]")
        return False

def test_installation():
    """Testuje instalację"""
    console.print("[yellow]Testowanie instalacji...[/yellow]")
    
    venv_python = get_venv_python()
    
    try:
        # Test importu modułów w środowisku wirtualnym
        test_script = """
import teslapy
import click
import rich
from dotenv import load_dotenv
import os

load_dotenv()
email = os.getenv('TESLA_EMAIL')
print(f"Email Tesla: {email}")
print("Wszystkie moduły załadowane pomyślnie!")
"""
        
        result = subprocess.run([venv_python, "-c", test_script], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            console.print("[green]✓ Wszystkie moduły załadowane pomyślnie[/green]")
            output_lines = result.stdout.strip().split('\n')
            for line in output_lines:
                if line.startswith("Email Tesla:"):
                    console.print(f"[blue]{line}[/blue]")
            return True
        else:
            console.print(f"[red]✗ Błąd testowania: {result.stderr}[/red]")
            return False
        
    except Exception as e:
        console.print(f"[red]✗ Błąd testowania: {e}[/red]")
        return False

def show_next_steps():
    """Wyświetla następne kroki"""
    venv_activate = "source venv/bin/activate" if os.name != 'nt' else "venv\\Scripts\\activate"
    
    next_steps = f"""
    🎉 Instalacja zakończona pomyślnie!
    
    Następne kroki:
    
    1. Aktywuj środowisko wirtualne:
       {venv_activate}
    
    2. Uruchom program główny:
       python3 run.py
    
    3. Lub użyj interfejsu CLI:
       python3 cli.py --help
    
    4. Sprawdź przykłady użycia:
       python3 examples.py
    
    5. Tryb interaktywny:
       python3 cli.py interactive
    
    ⚠️  Ważne uwagi:
    - Zawsze aktywuj środowisko wirtualne przed uruchomieniem programu
    - Przy pierwszym uruchomieniu program otworzy przeglądarkę do autoryzacji
    - Skopiuj URL z przeglądarki po zalogowaniu do Tesla
    - Token zostanie zapisany w pliku cache dla przyszłych użyć
    """
    
    console.print(Panel(next_steps, title="Gotowe!", border_style="green"))

def main():
    """Główna funkcja instalacyjna"""
    show_welcome()
    
    # Sprawdzenie wersji Pythona
    if not check_python_version():
        sys.exit(1)
    
    # Tworzenie środowiska wirtualnego
    if not create_virtual_environment():
        console.print("[red]Instalacja przerwana z powodu błędów.[/red]")
        sys.exit(1)
    
    # Instalacja zależności
    if not install_dependencies():
        console.print("[red]Instalacja przerwana z powodu błędów.[/red]")
        sys.exit(1)
    
    # Tworzenie pliku konfiguracyjnego
    if not create_env_file():
        console.print("[red]Instalacja przerwana z powodu błędów.[/red]")
        sys.exit(1)
    
    # Test instalacji
    if not test_installation():
        console.print("[yellow]Instalacja zakończona z ostrzeżeniami.[/yellow]")
    
    # Wyświetlenie następnych kroków
    show_next_steps()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Instalacja przerwana przez użytkownika.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Nieoczekiwany błąd: {e}[/red]") 