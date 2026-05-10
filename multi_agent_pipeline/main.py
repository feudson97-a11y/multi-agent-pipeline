"""
Point d'entrée du pipeline multi-agents.

Usage:
    python main.py "Analyse les tendances du marché de l'IA en 2025"
    python main.py "Rapport sur les LLMs open-source" --format report
    python main.py --interactive
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path


def check_env():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌  Variable ANTHROPIC_API_KEY manquante.")
        print("    Exportez-la: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)


async def run_pipeline(task: str, output_format: str, save_output: bool = False):
    from orchestrator import Orchestrator

    orchestrator = Orchestrator()
    run = await orchestrator.run(task, output_format=output_format)

    print("\n" + "="*60)
    print("RÉSULTAT FINAL")
    print("="*60)

    if run.final_output:
        print(run.final_output)
    else:
        print("Aucun output final généré.")

    if save_output and run.final_output:
        out_path = Path(f"output_{run.run_id}.{output_format if output_format != 'report' else 'md'}")
        out_path.write_text(str(run.final_output), encoding="utf-8")
        print(f"\n💾 Résultat sauvegardé: {out_path}")

    # Stats du run
    print(f"\n📊 Stats:")
    print(f"   run_id    : {run.run_id}")
    print(f"   status    : {run.status}")
    print(f"   itérations: {run.iteration}")
    agents_ran = list(run.results.keys())
    print(f"   agents    : {', '.join(agents_ran)}")

    return run


async def interactive_mode():
    """Mode interactif REPL."""
    print("\n🤖 Pipeline Multi-Agents — Mode Interactif")
    print("   Commandes: 'quit' pour quitter, 'format <fmt>' pour changer le format\n")

    output_format = "markdown"

    while True:
        try:
            task = input(f"[{output_format}] Tâche > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir!")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            print("Au revoir!")
            break
        if task.lower().startswith("format "):
            output_format = task.split(" ", 1)[1].strip()
            print(f"  Format changé: {output_format}")
            continue

        try:
            await run_pipeline(task, output_format, save_output=True)
        except Exception as e:
            print(f"\n❌ Erreur: {e}")


def main():
    check_env()

    parser = argparse.ArgumentParser(
        description="Pipeline multi-agents propulsé par Claude"
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="Tâche à exécuter (ex: 'Analyse les tendances IA en 2025')"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json", "plain_text", "html", "report"],
        default="markdown",
        help="Format de sortie (défaut: markdown)"
    )
    parser.add_argument(
        "--save", "-s",
        action="store_true",
        help="Sauvegarder le résultat dans un fichier"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Mode interactif (REPL)"
    )

    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive_mode())
    elif args.task:
        asyncio.run(run_pipeline(args.task, args.format, save_output=args.save))
    else:
        parser.print_help()
        print("\nExemples:")
        print('  python main.py "Analyse les tendances de l\'IA en 2025"')
        print('  python main.py "Rapport sur Python vs Go" --format report --save')
        print('  python main.py --interactive')


if __name__ == "__main__":
    main()
