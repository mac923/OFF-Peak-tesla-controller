#!/usr/bin/env python3
"""
CLI dla Tesla Controller
Interfejs wiersza poleceń do kontrolowania pojazdu Tesla
"""

import click
import sys
from rich.console import Console
from rich.prompt import Prompt, Confirm
from src.core.tesla_controller import TeslaController, ChargeSchedule

console = Console()

@click.group()
@click.option('--email', '-e', help='Adres email konta Tesla')
@click.option('--cache-file', '-c', help='Ścieżka do pliku cache')
@click.pass_context
def cli(ctx, email, cache_file):
    """Tesla Controller - Program do kontrolowania pojazdu Tesla"""
    ctx.ensure_object(dict)
    
    try:
        controller = TeslaController(email=email, cache_file=cache_file)
        if not controller.connect():
            console.print("[red]Nie udało się połączyć z Tesla API.[/red]")
            sys.exit(1)
        ctx.obj['controller'] = controller
    except Exception as e:
        console.print(f"[red]Błąd inicjalizacji: {e}[/red]")
        sys.exit(1)

@cli.command()
@click.pass_context
def status(ctx):
    """Wyświetla status pojazdu"""
    controller = ctx.obj['controller']
    controller.display_vehicle_status()

@cli.command()
@click.pass_context
def quick_status(ctx):
    """Wyświetla szybki status pojazdu bez budzenia (format: STATUS | BATTERY | CHARGING | LOCATION)"""
    controller = ctx.obj['controller']
    quick_status = controller.get_quick_status()
    console.print(f"[bold cyan]Szybki status:[/bold cyan] {quick_status}")

@cli.command()
@click.pass_context
def vehicles(ctx):
    """Wyświetla listę dostępnych pojazdów"""
    controller = ctx.obj['controller']
    controller.list_vehicles()

@cli.command()
@click.argument('index', type=int)
@click.pass_context
def select(ctx, index):
    """Wybiera pojazd do kontrolowania (indeks 1-based)"""
    controller = ctx.obj['controller']
    if controller.select_vehicle(index - 1):
        console.print(f"[green]Wybrano pojazd #{index}[/green]")

@cli.command()
@click.pass_context
def wake(ctx):
    """Budzi pojazd"""
    controller = ctx.obj['controller']
    controller.wake_up_vehicle()

@cli.command(name='check-auth')
@click.pass_context
def check_auth(ctx):
    """Sprawdza stan autoryzacji Tesla API"""
    controller = ctx.obj['controller']
    if hasattr(controller, 'check_authorization'):
        if controller.check_authorization():
            console.print("\n[green]🎉 Autoryzacja Tesla API działa prawidłowo![/green]")
        else:
            console.print("\n[red]⚠️  Wykryto problemy z autoryzacją Tesla API[/red]")
            console.print("[yellow]Uruchom 'python3 generate_token.py' aby naprawić autoryzację[/yellow]")
    else:
        console.print("[red]❌ Funkcja sprawdzania autoryzacji niedostępna[/red]")

@cli.command()
@click.argument('limit', type=int)
@click.pass_context
def set_limit(ctx, limit):
    """Ustawia limit ładowania baterii (50-100%)"""
    controller = ctx.obj['controller']
    controller.set_charge_limit(limit)

@cli.command()
@click.argument('amps', type=int)
@click.pass_context
def set_amps(ctx, amps):
    """Ustawia prąd ładowania w amperach"""
    controller = ctx.obj['controller']
    controller.set_charging_amps(amps)



@cli.command()
@click.option('--start-time', '-s', help='Czas rozpoczęcia ładowania (HH:MM)')
@click.option('--end-time', '-e', help='Czas zakończenia ładowania (HH:MM)')
@click.option('--days', '-d', default='All', help='Dni tygodnia (np. "All", "Weekdays", "Monday,Tuesday")')
@click.option('--enable/--disable', default=True, help='Włącz/wyłącz harmonogram ładowania')
@click.pass_context
def schedule_charge(ctx, start_time, end_time, days, enable):
    """
    Ustawia zaplanowane ładowanie z opcjonalnym czasem rozpoczęcia i zakończenia
    
    Przykłady:
    - schedule-charge --start-time 02:00                 # Tylko czas rozpoczęcia
    - schedule-charge --end-time 07:00                   # Tylko czas zakończenia  
    - schedule-charge --start-time 23:00 --end-time 07:00  # Pełne okno czasowe
    - schedule-charge --start-time 02:00 --days Weekdays   # Tylko dni robocze
    """
    controller = ctx.obj['controller']
    
    # Sprawdź czy podano przynajmniej jeden czas
    if not start_time and not end_time:
        console.print("[red]Błąd: Musisz podać przynajmniej --start-time lub --end-time[/red]")
        console.print("[blue]Przykłady:[/blue]")
        console.print("  schedule-charge --start-time 02:00")
        console.print("  schedule-charge --end-time 07:00") 
        console.print("  schedule-charge --start-time 23:00 --end-time 07:00")
        return
    
    # Stwórz harmonogram ładowania
    schedule = ChargeSchedule(
        days_of_week=days,
        enabled=enable,
        one_time=False
    )
    
    # Lokalizacja zostanie automatycznie ustawiona w add_charge_schedule()
    # za pomocą get_vehicle_location() - użyje lokalizacji pojazdu lub domyślnej z .env
    
    # Ustaw czas rozpoczęcia
    if start_time:
        schedule.start_enabled = True
        schedule.start_time = controller.time_to_minutes(start_time)
        console.print(f"[green]Czas rozpoczęcia: {start_time}[/green]")
    
    # Ustaw czas zakończenia
    if end_time:
        schedule.end_enabled = True
        schedule.end_time = controller.time_to_minutes(end_time)
        console.print(f"[green]Czas zakończenia: {end_time}[/green]")
    
    # Wyświetl informacje o harmonogramie
    console.print(f"[blue]Dni tygodnia: {days}[/blue]")
    console.print(f"[blue]Status: {'Włączony' if enable else 'Wyłączony'}[/blue]")
    
    # Dodaj harmonogram
    if controller.add_charge_schedule(schedule):
        console.print("[green]✓ Harmonogram ładowania został dodany pomyślnie![/green]")
        
        # Pokaż zaktualizowaną listę harmonogramów
        console.print("\n[yellow]Aktualne harmonogramy:[/yellow]")
        controller.display_charge_schedules()
    else:
        console.print("[red]✗ Błąd podczas dodawania harmonogramu ładowania[/red]")

@cli.command()
@click.pass_context
def schedules(ctx):
    """Wyświetla harmonogramy ładowania"""
    controller = ctx.obj['controller']
    controller.display_charge_schedules()

@cli.command()
@click.option('--start-time', '-s', help='Czas rozpoczęcia (HH:MM)')
@click.option('--end-time', '-e', help='Czas zakończenia (HH:MM)')
@click.option('--days', '-d', default='All', help='Dni tygodnia (np. "Monday,Tuesday" lub "All" lub "Weekdays")')
@click.option('--lat', type=float, default=0.0, help='Szerokość geograficzna')
@click.option('--lon', type=float, default=0.0, help='Długość geograficzna')
@click.option('--one-time', is_flag=True, help='Harmonogram jednorazowy')
@click.pass_context
def add_schedule(ctx, start_time, end_time, days, lat, lon, one_time):
    """Dodaje nowy harmonogram ładowania"""
    controller = ctx.obj['controller']
    
    schedule = ChargeSchedule(
        days_of_week=days,
        lat=lat,
        lon=lon,
        one_time=one_time
    )
    
    if start_time:
        schedule.start_enabled = True
        schedule.start_time = controller.time_to_minutes(start_time)
    
    if end_time:
        schedule.end_enabled = True
        schedule.end_time = controller.time_to_minutes(end_time)
    
    controller.add_charge_schedule(schedule)

@cli.command()
@click.argument('schedule_id', type=int)
@click.pass_context
def remove_schedule(ctx, schedule_id):
    """Usuwa harmonogram ładowania o podanym ID"""
    controller = ctx.obj['controller']
    controller.remove_charge_schedule(schedule_id)

@cli.command()
@click.option('--confirm', is_flag=True, help='Potwierdź usunięcie bez pytania')
@click.pass_context
def remove_all_schedules(ctx, confirm):
    """Usuwa wszystkie harmonogramy ładowania"""
    controller = ctx.obj['controller']
    
    if not confirm:
        if not Confirm.ask("[red]Czy na pewno chcesz usunąć WSZYSTKIE harmonogramy ładowania?[/red]"):
            console.print("[yellow]Operacja anulowana.[/yellow]")
            return
    
    controller.remove_all_charge_schedules()

@cli.command()
@click.pass_context
def interactive(ctx):
    """Tryb interaktywny"""
    controller = ctx.obj['controller']
    
    console.print("[bold blue]Tesla Controller - Tryb Interaktywny[/bold blue]")
    console.print("Dostępne komendy:")
    console.print("1. Status pojazdu")
    console.print("2. Lista pojazdów")
    console.print("3. Wybierz pojazd")
    console.print("4. Obudź pojazd")
    console.print("5. Ustaw limit ładowania")
    console.print("6. Ustaw prąd ładowania")
    console.print("7. Zaplanuj ładowanie")
    console.print("8. Pokaż harmonogramy")
    console.print("9. Dodaj harmonogram")
    console.print("10. Usuń harmonogram")
    console.print("11. Usuń wszystkie harmonogramy")
    console.print("0. Wyjście")
    
    while True:
        try:
            choice = Prompt.ask("\nWybierz opcję", choices=['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11'])
            
            if choice == '0':
                console.print("[yellow]Do widzenia![/yellow]")
                break
            elif choice == '1':
                controller.display_vehicle_status()
            elif choice == '2':
                controller.list_vehicles()
            elif choice == '3':
                controller.list_vehicles()
                index = int(Prompt.ask("Podaj numer pojazdu")) - 1
                controller.select_vehicle(index)
            elif choice == '4':
                controller.wake_up_vehicle()
            elif choice == '5':
                limit = int(Prompt.ask("Podaj limit ładowania (50-100%)", default="80"))
                controller.set_charge_limit(limit)
            elif choice == '6':
                amps = int(Prompt.ask("Podaj prąd ładowania (A)", default="16"))
                controller.set_charging_amps(amps)
            elif choice == '7':
                time_str = Prompt.ask("Podaj czas ładowania (HH:MM)", default="02:00")
                enable = Confirm.ask("Włączyć zaplanowane ładowanie?", default=True)
                controller.set_scheduled_charging(time_str, enable)
            elif choice == '8':
                controller.display_charge_schedules()
            elif choice == '9':
                console.print("[yellow]Dodawanie nowego harmonogramu ładowania[/yellow]")
                
                days = Prompt.ask("Dni tygodnia", default="All", 
                                show_default=True,
                                help_text="Przykłady: 'All', 'Weekdays', 'Monday,Wednesday,Friday'")
                
                start_enabled = Confirm.ask("Ustawić czas rozpoczęcia?", default=False)
                start_time = None
                if start_enabled:
                    start_time_str = Prompt.ask("Czas rozpoczęcia (HH:MM)", default="23:00")
                    start_time = controller.time_to_minutes(start_time_str)
                
                end_enabled = Confirm.ask("Ustawić czas zakończenia?", default=False)
                end_time = None
                if end_enabled:
                    end_time_str = Prompt.ask("Czas zakończenia (HH:MM)", default="07:00")
                    end_time = controller.time_to_minutes(end_time_str)
                
                one_time = Confirm.ask("Harmonogram jednorazowy?", default=False)
                
                schedule = ChargeSchedule(
                    days_of_week=days,
                    start_enabled=start_enabled,
                    start_time=start_time,
                    end_enabled=end_enabled,
                    end_time=end_time,
                    one_time=one_time
                )
                
                controller.add_charge_schedule(schedule)
                
            elif choice == '10':
                schedule_id = int(Prompt.ask("Podaj ID harmonogramu do usunięcia"))
                controller.remove_charge_schedule(schedule_id)
                
            elif choice == '11':
                controller.remove_all_charge_schedules()
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Przerwano przez użytkownika.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Błąd: {e}[/red]")

if __name__ == '__main__':
    cli() 