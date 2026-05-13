# Rudeus Bot — Cấu Trúc Mới

## Cách chạy
```
python main.py
```

## Cấu trúc file

```
rudeus/
├── main.py              # Khởi động bot, on_ready, load cogs
├── config.py            # Imports, constants (ADMIN_IDS, IDs...), helpers, DB, HELP_CATEGORIES
└── cogs/
    ├── ticket.py        # Ticket system, Seller management (.addseller .removeseller .listseller)
    ├── ticket_cmds.py   # .done .addnote .ratings .orderbase .qr
    ├── help_cmd.py      # .help
    ├── mod.py           # .clear .addrole .removerole .createchannel .deletechannel
    ├── giveaway.py      # .gstart .gend .greroll .gpick .gwlist + /giveaway /gend
    ├── info.py          # .botinfo .serverinfo .userinfo + slash equivalents
    ├── settings.py      # .settings, DangerousCommandsView
    ├── balance.py       # .balance .balreset .balset
    ├── ai_chat.py       # .ai .aireset .mychat
    ├── invite.py        # .invite .invitetop .resetinvite
    ├── events.py        # on_message, on_member_join, on_member_remove
    ├── setup.py         # .setup .setperm .rename .mkchannel
    ├── emoji.py         # .emoji .delemoji
    ├── price.py         # .sv .giaset
    └── slash_misc.py    # /clear /addrole /removerole /ping /qr ...
```

## Khi cần sửa tính năng

| Tính năng | File cần upload |
|-----------|----------------|
| Giveaway  | `cogs/giveaway.py` |
| Ticket    | `cogs/ticket.py` hoặc `cogs/ticket_cmds.py` |
| AI chat   | `cogs/ai_chat.py` |
| Emoji     | `cogs/emoji.py` |
| Bảng giá  | `cogs/price.py` |
| Help      | `cogs/help_cmd.py` |
| Settings  | `cogs/settings.py` |
| Hằng số / IDs | `config.py` |

## Biến môi trường
- `TOKEN` — Discord bot token (bắt buộc)
- `MONGO_URI` — MongoDB connection string (bắt buộc)
- `GROQ_API_KEY` — Groq API key cho AI chat (tuỳ chọn)
