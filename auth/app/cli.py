import argparse
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from .db import SessionLocal
from .models import Role, User, UserRole
from .security import hash_password

MIN_PASSWORD_LENGTH = 12


def _active_admin_exists(session) -> bool:
    statement = (
        select(UserRole.id)
        .join(Role, Role.id == UserRole.role_id)
        .join(User, User.id == UserRole.user_id)
        .where(
            Role.name == "ADMIN",
            Role.status == "active",
            UserRole.status == "active",
            User.status == "active",
        )
    )
    return session.scalar(statement) is not None


def _read_password(password_stdin: bool) -> str | None:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            print("error: no se recibió contraseña por stdin", file=sys.stderr)
            return None
        return password
    password = getpass.getpass("Contraseña del administrador: ")
    if password != getpass.getpass("Repite la contraseña: "):
        print("error: las contraseñas no coinciden", file=sys.stderr)
        return None
    return password


def bootstrap_admin(args: argparse.Namespace) -> int:
    password = _read_password(args.password_stdin)
    if password is None:
        return 2
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"error: la contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres", file=sys.stderr)
        return 2

    with SessionLocal(expire_on_commit=False) as session:
        if _active_admin_exists(session):
            print("ya existe un ADMIN activo; no se crea otro")
            return 0

        role = session.scalar(select(Role).where(Role.name == "ADMIN"))
        if role is None:
            print("error: falta la semilla de roles; aplica db/auth/001_init.sql", file=sys.stderr)
            return 3

        user = User(
            username=args.username,
            email=args.email,
            password_hash=hash_password(password),
            status="active",
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id, status="active"))
        session.commit()

        print(f"ADMIN creado: {user.username} ({user.id})")
        print(
            f"audit bootstrap_admin_created user_id={user.id} at={datetime.now(timezone.utc).isoformat()}"
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser(
        "bootstrap-admin", help="crea el primer ADMIN si no existe ninguno activo"
    )
    bootstrap.add_argument("--username", default="admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument(
        "--password-stdin",
        action="store_true",
        help="lee la contraseña de la entrada estándar en lugar de pedirla por teclado",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "bootstrap-admin":
        return bootstrap_admin(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
