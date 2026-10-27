"""Local administration: python -m app.manage claim-legacy <username>."""
import argparse

from app.config import Settings
from app.repository import DecisionRepository


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='VeriPlan 数据管理')
    commands = parser.add_subparsers(dest='command', required=True)
    claim = commands.add_parser('claim-legacy', help='把无归属决策归给已有用户')
    claim.add_argument('username')
    args = parser.parse_args(argv)
    repository = DecisionRepository(Settings().database_url)
    try:
        count = repository.claim_legacy(args.username)
        print(f'已归属 {count} 条决策')
    except ValueError as error:
        parser.error(str(error))
    finally:
        repository._engine.dispose()


if __name__ == '__main__':
    main()
