#!/usr/bin/env python3
"""
Node Modules Cleaner - Find and clean node_modules directories on macOS
Handles hardlinks properly to show both actual and estimated disk usage.
Inspired by npkill for performance and UX.
"""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
# from queue import Queue
# from typing import Optional

# ANSI escape codes for terminal control
CLEAR_LINE = "\033[2K"
MOVE_UP = "\033[1A"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


@dataclass
class NodeModulesInfo:
    """Information about a node_modules directory."""

    path: Path
    apparent_size: int = 0  # Size counting all files
    actual_size: int = 0  # Actual disk usage
    file_count: int = 0
    analyzed: bool = False

    @property
    def apparent_size_human(self) -> str:
        return format_size(self.apparent_size)

    @property
    def actual_size_human(self) -> str:
        return format_size(self.actual_size)


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def truncate_path(path: str, max_depth: int = 3, max_len: int = 60) -> str:
    """Truncate path to show only last N depth levels."""
    parts = Path(path).parts
    if len(parts) <= max_depth:
        result = str(path)
    else:
        result = os.path.join("...", *parts[-max_depth:])

    if len(result) > max_len:
        result = "..." + result[-(max_len - 3) :]
    return result


class ProgressDisplay:
    """Thread-safe progress display."""

    def __init__(self):
        self.current_dir = ""
        self.found_count = 0
        self.searched_count = 0
        self.lock = threading.Lock()
        self.running = True
        self.last_update = 0
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_idx = 0

    def update(self, current_dir: str, found: int, searched: int):
        """Update progress info."""
        with self.lock:
            self.current_dir = current_dir
            self.found_count = found
            self.searched_count = searched

    def display(self):
        """Display current progress."""
        with self.lock:
            spinner = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
            self.spinner_idx += 1

            truncated = truncate_path(self.current_dir, max_depth=3, max_len=55)

            status = f"\r{CLEAR_LINE}{spinner} Recherche... {self.found_count} trouvés | {self.searched_count} dossiers | {truncated}"
            print(status, end="", flush=True)

    def stop(self):
        """Stop the display."""
        self.running = False
        print(f"\r{CLEAR_LINE}", end="", flush=True)


def find_node_modules_fast(start_path: Path, progress: ProgressDisplay) -> list[Path]:
    """
    Find all node_modules directories using os.scandir for performance.

    Uses iterative approach with stack to avoid recursion limits.
    Skips system directories and nested node_modules.
    """
    node_modules: list[Path] = []

    # Directories to skip entirely
    skip_dirs = {
        ".git",
        ".svn",
        ".hg",
        "Library",
        "System",
        "Applications",
        ".Trash",
        ".cache",
        ".npm",
        ".yarn",
        "Caches",
        "Containers",
        "Logs",
        ".local",
        ".config",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".tox",
        "Volumes",  # Skip mounted volumes
    }

    # Stack-based traversal (faster than recursion)
    stack = [start_path]
    searched_count = 0

    while stack and progress.running:
        try:
            current = stack.pop()
            searched_count += 1

            # Update progress every 50 dirs for performance
            if searched_count % 50 == 0:
                progress.update(str(current), len(node_modules), searched_count)

            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if not entry.is_dir(follow_symlinks=False):
                                continue

                            name = entry.name

                            # Skip hidden and system directories
                            if name.startswith(".") and name not in {"."}:
                                if name not in {".node_modules"}:  # Keep looking
                                    continue

                            if name in skip_dirs:
                                continue

                            entry_path = Path(entry.path)

                            if name == "node_modules":
                                node_modules.append(entry_path)
                                progress.update(str(current), len(node_modules), searched_count)
                                # Don't descend into node_modules
                                continue

                            # Add to stack for processing
                            stack.append(entry_path)

                        except (PermissionError, OSError):
                            continue

            except (PermissionError, OSError):
                continue

        except KeyboardInterrupt:
            progress.running = False
            break

    return node_modules


def get_size_fast(path: Path) -> tuple[int, int, int]:
    """
    Get directory sizes quickly using du for actual size
    and os.scandir for apparent size (handles hardlinks).

    Returns: (actual_size, apparent_size, file_count)
    """
    try:
        # Use du for actual disk usage (fast)
        result = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, timeout=30)
        try:
            actual_size = int(result.stdout.strip().split()[0]) * 1024
        except (ValueError, IndexError):
            actual_size = 0

        # Quick apparent size calculation using scandir
        apparent_size = 0
        file_count = 0

        stack = [path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                apparent_size += entry.stat(follow_symlinks=False).st_size
                                file_count += 1
                            elif entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        return actual_size, apparent_size, file_count

    except Exception:
        return 0, 0, 0


def analyze_parallel(paths: list[Path], max_workers: int = 4) -> list[NodeModulesInfo]:
    """Analyze node_modules in parallel for speed."""
    results = [NodeModulesInfo(path=p) for p in paths]
    total = len(paths)
    completed = 0

    print(f"\n📊 Analyse de {total} dossiers node_modules...\n")

    def analyze_one(idx: int, info: NodeModulesInfo):
        actual, apparent, count = get_size_fast(info.path)
        info.actual_size = actual
        info.apparent_size = apparent
        info.file_count = count
        info.analyzed = True
        return idx

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_one, i, info): i for i, info in enumerate(results)}

        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            info = results[idx]

            # Truncate path for display
            path_display = truncate_path(str(info.path), max_depth=2, max_len=40)

            print(
                f"\r{CLEAR_LINE}   [{completed}/{total}] {path_display} → {info.actual_size_human}", end="", flush=True
            )

    print(f"\r{CLEAR_LINE}   ✅ Analyse terminée!")
    return results


def print_summary(infos: list[NodeModulesInfo]) -> None:
    """Print a summary of all found node_modules."""
    if not infos:
        print("❌ Aucun dossier node_modules trouvé.")
        return

    # Sort by actual size, descending
    infos.sort(key=lambda x: x.actual_size, reverse=True)

    total_actual = sum(i.actual_size for i in infos)
    total_apparent = sum(i.apparent_size for i in infos)

    print("\n" + "=" * 100)
    print("📦 DOSSIERS NODE_MODULES TROUVÉS")
    print("=" * 100)
    print()
    print(f"{'#':<4} {'Chemin':<50} {'Taille réelle':<15} {'Taille estimée':<15} {'Fichiers':<10}")
    print("-" * 100)

    for i, info in enumerate(infos, 1):
        path_str = truncate_path(str(info.path), max_depth=4, max_len=48)
        print(
            f"{i:<4} {path_str:<50} {info.actual_size_human:<15} {info.apparent_size_human:<15} {info.file_count:<10}"
        )

    print("-" * 100)
    print(f"{'TOTAL':<4} {'':<50} {format_size(total_actual):<15} {format_size(total_apparent):<15}")
    print()
    
    if total_apparent > total_actual:
        savings = total_apparent - total_actual
        print(f"💡 Économie grâce aux hardlinks: {format_size(savings)} ({(savings / total_apparent) * 100:.1f}%)")
    print()


def interactive_selection(infos: list[NodeModulesInfo]) -> list[NodeModulesInfo]:
    """Interactive CLI for selecting node_modules to delete."""
    if not infos:
        return []

    selected: set[int] = set()

    while True:
        os.system("clear" if os.name != "nt" else "cls")

        total_selected_actual = sum(infos[i].actual_size for i in selected)
        total_selected_apparent = sum(infos[i].apparent_size for i in selected)

        print("\n" + "=" * 110)
        print("🗑️  SÉLECTION DES DOSSIERS À SUPPRIMER")
        print("=" * 110)
        print()
        print(
            f"  Sélectionnés: {len(selected)}/{len(infos)} | "
            f"Espace réel: {format_size(total_selected_actual)} | "
            f"Espace estimé: {format_size(total_selected_apparent)}"
        )
        print()
        print(f"{'#':<4} {'[X]':<5} {'Chemin':<55} {'Taille réelle':<15} {'Taille estimée':<15}")
        print("-" * 110)

        for i, info in enumerate(infos):
            check = "[X]" if i in selected else "[ ]"
            path_str = truncate_path(str(info.path), max_depth=4, max_len=53)
            print(f"{i + 1:<4} {check:<5} {path_str:<55} {info.actual_size_human:<15} {info.apparent_size_human:<15}")

        print("-" * 110)
        print()
        print("Commandes:")
        print("  <numéro>     - Basculer la sélection (ex: 1, 1-5, 1 3 5)")
        print("  a            - Tout sélectionner")
        print("  n            - Tout désélectionner")
        print("  d            - Supprimer les sélectionnés")
        print("  q            - Quitter sans supprimer")
        print()

        try:
            choice = input("Votre choix: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAnnulé.")
            return []

        if choice == "q":
            return []
        elif choice == "a":
            selected = set(range(len(infos)))
        elif choice == "n":
            selected = set()
        elif choice == "d":
            if selected:
                return [infos[i] for i in sorted(selected)]
            else:
                print("⚠️  Aucun dossier sélectionné!")
                input("Appuyez sur Entrée pour continuer...")
        else:
            try:
                # Handle ranges like "1-5" or multiple numbers like "1 2 3"
                if "-" in choice:
                    start, end = map(int, choice.split("-"))
                    for num in range(start, end + 1):
                        if 1 <= num <= len(infos):
                            idx = num - 1
                            if idx in selected:
                                selected.remove(idx)
                            else:
                                selected.add(idx)
                elif " " in choice:
                    for num_str in choice.split():
                        num = int(num_str)
                        if 1 <= num <= len(infos):
                            idx = num - 1
                            if idx in selected:
                                selected.remove(idx)
                            else:
                                selected.add(idx)
                else:
                    num = int(choice)
                    if 1 <= num <= len(infos):
                        idx = num - 1
                        if idx in selected:
                            selected.remove(idx)
                        else:
                            selected.add(idx)
                    else:
                        print(f"⚠️  Numéro invalide: {num}")
                        input("Appuyez sur Entrée pour continuer...")
            except ValueError:
                print(f"⚠️  Commande invalide: {choice}")
                input("Appuyez sur Entrée pour continuer...")


def delete_directories(to_delete: list[NodeModulesInfo]) -> None:
    """Delete the selected directories."""
    if not to_delete:
        return

    total_actual = sum(i.actual_size for i in to_delete)
    total_apparent = sum(i.apparent_size for i in to_delete)

    print(f"\n⚠️  Vous êtes sur le point de supprimer {len(to_delete)} dossiers:")
    print(f"   Espace réel à libérer: {format_size(total_actual)}")
    print(f"   Espace estimé à libérer: {format_size(total_apparent)}")
    print()

    for info in to_delete:
        print(f"   • {info.path}")

    print()
    try:
        confirm = input("Confirmer la suppression? (oui/non): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAnnulé.")
        return

    if confirm not in ["oui", "o", "yes", "y"]:
        print("Suppression annulée.")
        return

    print()
    deleted_count = 0
    deleted_size = 0

    for info in to_delete:
        print(f"🗑️  Suppression de {truncate_path(str(info.path), 3, 50)}...", end=" ", flush=True)
        try:
            shutil.rmtree(info.path)
            print("✅")
            deleted_count += 1
            deleted_size += info.actual_size
        except PermissionError:
            print("❌ Permission refusée")
        except Exception as e:
            print(f"❌ Erreur: {e}")

    print()
    print(f"✨ {deleted_count}/{len(to_delete)} dossiers supprimés")
    print(f"💾 Espace libéré: ~{format_size(deleted_size)}")


def main():
    """Main entry point."""

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{SHOW_CURSOR}Interrompu par l'utilisateur.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║          🧹 NODE MODULES CLEANER pour macOS                ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print("║  Trouve et nettoie les dossiers node_modules               ║")
    print("║  Prend en compte les hardlinks pour l'espace réel          ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # Default to home directory
    default_path = Path.home()

    if len(sys.argv) > 1:
        search_path = Path(sys.argv[1])
    else:
        print(f"\nChemin de recherche (défaut: {default_path}): ", end="")
        try:
            user_input = input().strip()
            search_path = Path(user_input) if user_input else default_path
        except (KeyboardInterrupt, EOFError):
            print("\nAnnulé.")
            return

    if not search_path.exists():
        print(f"❌ Le chemin {search_path} n'existe pas.")
        return

    # Initialize progress display
    progress = ProgressDisplay()

    # Start spinner in background thread
    def spinner_thread():
        while progress.running:
            progress.display()
            time.sleep(0.1)

    print(f"\n🔍 Recherche dans {search_path}...\n")
    print(HIDE_CURSOR, end="")

    spinner = threading.Thread(target=spinner_thread, daemon=True)
    spinner.start()

    try:
        # Find all node_modules
        node_modules = find_node_modules_fast(search_path, progress)
    finally:
        progress.stop()
        print(SHOW_CURSOR, end="")

    if not node_modules:
        print("❌ Aucun dossier node_modules trouvé.")
        return

    print(f"✅ {len(node_modules)} dossiers node_modules trouvés")

    # Analyze them in parallel
    infos = analyze_parallel(node_modules)

    # Print summary
    print_summary(infos)

    # Interactive selection
    try:
        proceed = input("Voulez-vous sélectionner des dossiers à supprimer? (o/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAu revoir!")
        return

    if proceed in ["o", "oui", "y", "yes"]:
        to_delete = interactive_selection(infos)
        if to_delete:
            delete_directories(to_delete)

    print("\n👋 Au revoir!\n")


if __name__ == "__main__":
    main()
