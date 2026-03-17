# -*- coding: utf-8 -*-
"""Gate channel mapping for the YouTube 4-gate pipeline."""

import os

GATE_CHANNELS = {
    0: os.getenv("MATTERMOST_CHANNEL_PLAN_ID"),
    1: os.getenv("MATTERMOST_CHANNEL_NEWS_ID"),
    2: os.getenv("MATTERMOST_CHANNEL_SCRIPT_ID"),
    3: os.getenv("MATTERMOST_CHANNEL_VOICEOVER_ID"),
}
