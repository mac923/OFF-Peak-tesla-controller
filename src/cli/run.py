#!/usr/bin/env python3
"""
Tesla Controller - Główny skrypt uruchomieniowy
Prosty interfejs do wyboru trybu działania programu
"""

import sys
import os
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

def show_banner():
    """Wyświetla banner programu"""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                        TESLA CONTROLLER                      ║
    ║                                                              ║
    ║        Program do kontrolowania pojazdu Tesla                ║
    ║        Sprawdzanie parametrów i zarządzanie ładowaniem       ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold blue")

def check_requirements():
    """Sprawdza czy wszystkie wymagania są spełnione"""
    try:
        import click
        import rich
        from dotenv import load_dotenv
        from src.core.tesla_fleet_api_client import TeslaFleetAPIClient
        return True
    except ImportError as e:
        console.print(f"[red]Błąd: Brak wymaganej biblioteki: {e}[/red]")
        console.print("[yellow]Uruchom: pip3 install -r requirements.txt[/yellow]")
        console.print("[yellow]Upewnij się, że plik tesla_fleet_api_client.py istnieje[/yellow]")
        return False

def check_config():
    """Sprawdza konfigurację Fleet API"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Sprawdzenie wymaganych parametrów Fleet API
    required_vars = [
        'TESLA_CLIENT_ID',
        'TESLA_CLIENT_SECRET', 
        'TESLA_DOMAIN',
        'TESLA_PRIVATE_KEY_FILE',
        'TESLA_PUBLIC_KEY_URL'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        console.print("[red]Brak wymaganej konfiguracji Fleet API w pliku .env:[/red]")
        for var in missing_vars:
            console.print(f"[yellow]  {var}[/yellow]")
        console.print("\n[blue]Przykład konfiguracji .env:[/blue]")
        console.print("TESLA_CLIENT_ID=twój_client_id")
        console.print("TESLA_CLIENT_SECRET=twój_client_secret")
        console.print("TESLA_DOMAIN=twoja_domena.com")
        console.print("TESLA_PRIVATE_KEY_FILE=private-key.pem")
        console.print("TESLA_PUBLIC_KEY_URL=https://twoja_domena.com/.well-known/appspecific/com.tesla.3p.public-key.pem")
        return False
    else:
        console.print(f"[green]Konfiguracja Fleet API OK - Domena: {os.getenv('TESLA_DOMAIN')}[/green]")
        return True

def main_menu():
    """Główne menu programu"""
    show_banner()
    
    # Sprawdzenie wymagań
    if not check_requirements():
        sys.exit(1)
    
    # Sprawdzenie konfiguracji
    config_ok = check_config()
    
    console.print("\n[bold]Wybierz tryb działania:[/bold]")
    console.print("1. 🚗 Tryb interaktywny (menu)")
    console.print("2. 📊 Sprawdź status pojazdu")
    console.print("3. 🔋 Zarządzanie ładowaniem")
    console.print("4. ⏰ Harmonogramy ładowania")
    console.print("5. 📖 Przykłady użycia")
    console.print("6. 💻 Interfejs CLI (pomoc)")
    console.print("0. ❌ Wyjście")
    
    choice = Prompt.ask("\nWybierz opcję", choices=['0', '1', '2', '3', '4', '5', '6'])
    
    if choice == '0':
        console.print("[yellow]Do widzenia![/yellow]")
        sys.exit(0)
    elif choice == '1':
        run_interactive()
    elif choice == '2':
        run_status_check()
    elif choice == '3':
        run_charge_management()
    elif choice == '4':
        run_schedule_management()
    elif choice == '5':
        run_examples()
    elif choice == '6':
        show_cli_help()

def run_interactive():
    """Uruchamia tryb interaktywny"""
    console.print("[blue]Uruchamianie trybu interaktywnego...[/blue]")
    os.system("python3 cli.py interactive")

def run_status_check():
    """Sprawdza status pojazdu"""
    console.print("[blue]Sprawdzanie statusu pojazdu...[/blue]")
    os.system("python3 cli.py status")

def run_charge_management():
    """Menu zarządzania ładowaniem"""
    console.print("\n[bold]Zarządzanie ładowaniem:[/bold]")
    console.print("1. Sprawdź status ładowania")
    console.print("2. Rozpocznij ładowanie")
    console.print("3. Zatrzymaj ładowanie")
    console.print("4. Ustaw limit ładowania")
    console.print("5. Ustaw prąd ładowania")
    console.print("0. Powrót")
    
    choice = Prompt.ask("Wybierz opcję", choices=['0', '1', '2', '3', '4', '5'])
    
    if choice == '0':
        return
    elif choice == '1':
        os.system("python3 cli.py status")
    elif choice == '2':
        os.system("python3 cli.py start-charge")
    elif choice == '3':
        os.system("python3 cli.py stop-charge")
    elif choice == '4':
        limit = Prompt.ask("Podaj limit ładowania (50-100%)", default="80")
        os.system(f"python3 cli.py set-limit {limit}")
    elif choice == '5':
        amps = Prompt.ask("Podaj prąd ładowania (A)", default="16")
        os.system(f"python3 cli.py set-amps {amps}")

def run_schedule_management():
    """Menu harmonogramów ładowania"""
    console.print("\n[bold]Harmonogramy ładowania:[/bold]")
    console.print("1. Pokaż harmonogramy")
    console.print("2. Ustaw proste zaplanowane ładowanie")
    console.print("3. Dodaj harmonogram nocny (23:00-07:00)")
    console.print("4. Dodaj harmonogram weekendowy")
    console.print("5. Usuń harmonogram (po ID)")
    console.print("6. Usuń wszystkie harmonogramy")
    console.print("0. Powrót")
    
    choice = Prompt.ask("Wybierz opcję", choices=['0', '1', '2', '3', '4', '5', '6'])
    
    if choice == '0':
        return
    elif choice == '1':
        os.system("python3 cli.py schedules")
    elif choice == '2':
        console.print("\n[bold]Zaplanowane ładowanie:[/bold]")
        console.print("1. Tylko czas rozpoczęcia")
        console.print("2. Tylko czas zakończenia") 
        console.print("3. Pełne okno czasowe (start + end)")
        
        sub_choice = Prompt.ask("Wybierz typ", choices=['1', '2', '3'])
        
        if sub_choice == '1':
            time = Prompt.ask("Podaj czas rozpoczęcia (HH:MM)", default="02:00")
            os.system(f"python3 cli.py schedule-charge --start-time {time}")
        elif sub_choice == '2':
            time = Prompt.ask("Podaj czas zakończenia (HH:MM)", default="07:00")
            os.system(f"python3 cli.py schedule-charge --end-time {time}")
        elif sub_choice == '3':
            start_time = Prompt.ask("Podaj czas rozpoczęcia (HH:MM)", default="23:00")
            end_time = Prompt.ask("Podaj czas zakończenia (HH:MM)", default="07:00")
            os.system(f"python3 cli.py schedule-charge --start-time {start_time} --end-time {end_time}")
    elif choice == '3':
        os.system("python3 cli.py schedule-charge --start-time 23:00 --end-time 07:00")
        console.print("[green]Dodano harmonogram nocny (23:00-07:00)[/green]")
    elif choice == '4':
        os.system("python3 cli.py schedule-charge --start-time 10:00 --end-time 14:00 --days Saturday,Sunday")
        console.print("[green]Dodano harmonogram weekendowy (10:00-14:00)[/green]")
    elif choice == '5':
        id = Prompt.ask("Podaj ID harmonogramu do usunięcia")
        os.system(f"python3 cli.py remove-schedule {id}")
    elif choice == '6':
        os.system("python3 cli.py remove-all-schedules")
        console.print("[green]Usunięto wszystkie harmonogramy[/green]")

def run_examples():
    """Uruchamia przykłady"""
    console.print("[blue]Przykłady użycia Tesla Controller:[/blue]")
    console.print("\n[bold]Podstawowe komendy:[/bold]")
    examples = [
        "python3 cli.py status                              # Status pojazdu",
        "python3 cli.py vehicles                            # Lista pojazdów", 
        "python3 cli.py set-limit 80                        # Limit ładowania 80%",
        "python3 cli.py start-charge                        # Rozpocznij ładowanie",
        "python3 cli.py stop-charge                         # Zatrzymaj ładowanie",
        "python3 cli.py schedule-charge --start-time 02:00  # Zaplanuj start na 2:00",
        "python3 cli.py schedule-charge --start-time 23:00 --end-time 07:00  # Okno 23:00-07:00",
        "python3 cli.py schedules                           # Pokaż harmonogramy",
        "python3 cli.py interactive                         # Tryb interaktywny"
    ]
    
    for example in examples:
        console.print(f"  {example}")
    
    console.print(f"\n[yellow]Więcej informacji w dokumentacji: documentation/[/yellow]")
    input("\nNaciśnij Enter aby kontynuować...")

def show_cli_help():
    """Pokazuje pomoc CLI"""
    console.print("[blue]Dostępne komendy CLI:[/blue]")
    os.system("python3 cli.py --help")
    
    console.print("\n[blue]Przykłady użycia:[/blue]")
    examples = [
        "python3 cli.py status                              # Status pojazdu",
        "python3 cli.py vehicles                            # Lista pojazdów",
        "python3 cli.py set-limit 80                        # Limit ładowania 80%",
        "python3 cli.py start-charge                        # Rozpocznij ładowanie",
        "python3 cli.py stop-charge                         # Zatrzymaj ładowanie",
        "python3 cli.py schedule-charge --start-time 02:00  # Zaplanuj start na 2:00",
        "python3 cli.py schedule-charge --start-time 23:00 --end-time 07:00  # Okno 23:00-07:00",
        "python3 cli.py schedules                           # Pokaż harmonogramy",
        "python3 cli.py interactive                         # Tryb interaktywny"
    ]
    
    for example in examples:
        console.print(f"  {example}")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Przerwano przez użytkownika.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Błąd: {e}[/red]") 