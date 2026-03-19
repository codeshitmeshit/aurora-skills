# 🌅 Aurora Skills

A collection of AI agent skills for [OpenClaw](https://github.com/openclaw/openclaw).

## Skills

| Skill | Description | Status |
|-------|-------------|--------|
| [pulse](./skills/pulse/) | 📡 每日信息简报 — Product Hunt、GitHub Trending、新闻、播客、股票、天气 | ✅ Ready |

## Installation

```bash
# Copy skill to your OpenClaw skills directory
cp -r skills/pulse ~/.openclaw/skills/

# Install Python dependencies (for prefetch script)
cd ~/.openclaw/skills/pulse/scripts
pip install -r requirements.txt
```

## Usage

In your OpenClaw chat:
```
/pulse
```

Or set up a cron job for automatic daily briefings (morning 7:30 + evening 17:30).

## License

MIT
