import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _normalise_alias(
    value: str,
) -> str:
    text = str(
        value
        or ""
    ).strip().lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def get_steam_alias_store_path() -> Path:
    explicit = str(
        os.environ.get(
            "MAIRON_STEAM_ALIAS_PATH",
            "",
        )
        or ""
    ).strip()

    if explicit:
        return Path(
            explicit
        ).expanduser()

    project_root = str(
        os.environ.get(
            "MAIRON_PROJECT_ROOT",
            r"C:\Projects\Mairon",
        )
        or ""
    ).strip()

    return (
        Path(
            project_root
        )
        / "data"
        / "private"
        / "steam_game_aliases.json"
    )


def _load_store() -> dict:
    path = get_steam_alias_store_path()

    if not path.is_file():
        return {
            "version": 1,
            "aliases": {},
        }

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except Exception:
        return {
            "version": 1,
            "aliases": {},
        }

    aliases = data.get(
        "aliases"
    )

    if not isinstance(
        aliases,
        dict,
    ):
        aliases = {}

    return {
        "version": 1,
        "aliases": aliases,
    }


def _save_store(
    data: dict,
) -> None:
    path = get_steam_alias_store_path()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = json.dumps(
        data,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="steam_aliases_",
        suffix=".tmp",
        dir=str(
            path.parent
        ),
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                payload
            )
            handle.write(
                "\n"
            )

        os.replace(
            temp_name,
            path,
        )

    finally:
        try:
            if os.path.exists(
                temp_name
            ):
                os.unlink(
                    temp_name
                )
        except Exception:
            pass


def get_steam_game_alias(
    alias: str,
) -> Optional[dict]:
    key = _normalise_alias(
        alias
    )

    if not key:
        return None

    store = _load_store()

    entry = store[
        "aliases"
    ].get(
        key
    )

    if not isinstance(
        entry,
        dict,
    ):
        return None

    appid = str(
        entry.get(
            "appid",
            "",
        )
        or ""
    ).strip()

    game_name = str(
        entry.get(
            "game_name",
            "",
        )
        or ""
    ).strip()

    if (
        not appid.isdigit()
        or not game_name
    ):
        return None

    return {
        "alias": key,
        "appid": appid,
        "game_name": game_name,
        "updated_at": entry.get(
            "updated_at"
        ),
    }


def set_steam_game_alias(
    alias: str,
    appid: str,
    game_name: str,
) -> bool:
    key = _normalise_alias(
        alias
    )

    appid_value = str(
        appid
        or ""
    ).strip()

    game_name_value = str(
        game_name
        or ""
    ).strip()

    # Avoid useless/unsafe one-character aliases.
    if (
        len(
            key
        ) < 2
        or not appid_value.isdigit()
        or not game_name_value
    ):
        return False

    store = _load_store()

    store[
        "aliases"
    ][
        key
    ] = {
        "appid": appid_value,
        "game_name": game_name_value,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    _save_store(
        store
    )

    return True


def delete_steam_game_alias(
    alias: str,
) -> bool:
    key = _normalise_alias(
        alias
    )

    if not key:
        return False

    store = _load_store()

    if key not in store[
        "aliases"
    ]:
        return False

    del store[
        "aliases"
    ][
        key
    ]

    _save_store(
        store
    )

    return True
