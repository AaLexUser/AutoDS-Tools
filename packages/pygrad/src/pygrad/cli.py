"""Pygrad CLI entry point."""

import argparse
import asyncio
import sys

import pygrad as pg
from pygrad import get_repository_id


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Pygrad - Graph RAG API Doc", prog="pygrad")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add repository to knowledge graph")
    add_parser.add_argument("url", help="Repository URL")

    # Ask command
    ask_parser = subparsers.add_parser("ask", help="Query repository knowledge graph")
    ask_parser.add_argument("url", help="Repository URL")
    ask_parser.add_argument("query", help="Search query")

    # List command
    subparsers.add_parser("list", help="List indexed repositories")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete repository from knowledge graph")
    delete_parser.add_argument("url", help="Repository URL")

    # Visualize command
    vis_parser = subparsers.add_parser("visualize", help="Visualize knowledge graph")
    vis_parser.add_argument("-o", "--output", default="./pygrad.html", help="Output path")

    args = parser.parse_args()

    if args.command == "add":
        try:
            asyncio.run(pg.add(args.url))
            print(f"Successfully added repository: {args.url}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "ask":
        try:
            result = asyncio.run(pg.search(args.url, args.query))
            print(result)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        try:
            datasets = asyncio.run(pg.list())
            if datasets:
                for ds in datasets:
                    print(ds.name)
            else:
                print("No repositories indexed.")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "delete":
        try:
            asyncio.run(pg.delete(args.url))
            print(f"Successfully deleted: {get_repository_id(args.url)}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "visualize":
        try:
            path = asyncio.run(pg.visualize(args.output))
            print(f"Visualization saved to: {path}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(0 if args.command is None else 1)


if __name__ == "__main__":
    main()
