# Custom Prompt Overrides

Place your custom `.md` prompt files here to override any built-in skill prompt.

## How It Works

When the prompt loader loads a skill (e.g., `planner`), it checks:
1. `custom/planner.md` — your custom version (checked first)
2. `../planner.md` — built-in default (fallback)

This means you can override any prompt without modifying the originals.

## File Format

Each `.md` file should have two sections:

```markdown
<!-- SYSTEM -->
Your system prompt here...

<!-- USER -->
Your user prompt here with {template_variables}...
```

## Available Skills to Override

| Skill | Description |
|-------|-------------|
| `planner.md` | Content planning — topic selection, angle, budget |
| `writer.md` | Script writing — system prompt shared by all variants |
| `writer_trending_news.md` | Trending news script template |
| `writer_game_spotlight.md` | Game spotlight script template |
| `writer_hardware_spotlight.md` | Hardware spotlight script template |
| `writer_trailer_reaction.md` | Trailer reaction script template |
| `validator.md` | Script quality validation — scoring criteria |
| `seo.md` | SEO optimization — hashtags, captions |
| `clip.md` | Clip planning — footage selection |

## Example: Custom Writer

To create a custom trending news writer:

```bash
cp ../writer_trending_news.md custom/writer_trending_news.md
# Edit custom/writer_trending_news.md with your changes
```

## Template Variables

Use `{variable_name}` syntax. Available variables depend on the skill:

- **planner**: `{trending_games}`, `{remaining_budget}`, `{recent_topics}`
- **writer**: `{news_data}`, `{duration}`, `{content_type}`, `{revision_feedback}`
- **validator**: `{script_text}`, `{intended_duration}`
- **seo**: `{script_text}`, `{platform}`
- **clip**: `{script_text}`, `{available_games}`
