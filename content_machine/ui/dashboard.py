"""
Modern Bento Grid & Kanban HTML Report / Canvas Generator for Content Machine.
Generates a standalone, interactive dashboard with an editable script canvas,
searchable research dossier, and asset pipeline file placeholders.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.models import ResearchDossier


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Content Machine | __ROOT_TOPIC__</title>
    <style>
        :root {
            --bg: #090d16;
            --surface: rgba(18, 24, 38, 0.85);
            --surface-hover: rgba(28, 36, 56, 0.95);
            --border: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(255, 255, 255, 0.18);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-cyan: #06b6d4;
            --accent-blue: #3b82f6;
            --accent-violet: #8b5cf6;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
            --radius-lg: 16px;
            --radius-md: 10px;
            --radius-sm: 6px;
            --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.12) 0px, transparent 50%),
                radial-gradient(at 50% 50%, rgba(6, 182, 212, 0.05) 0px, transparent 70%);
            background-attachment: fixed;
            color: var(--text-primary);
            font-family: var(--font);
            line-height: 1.5;
            padding: 24px;
            min-height: 100vh;
        }

        /* Header Navigation */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-badge {
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            font-weight: 800;
            font-size: 0.85rem;
            letter-spacing: 1px;
            text-transform: uppercase;
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.4);
        }

        .topic-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .header-actions {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 14px;
            border-radius: var(--radius-sm);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
        }

        .btn:hover {
            background: var(--surface-hover);
            border-color: var(--border-hover);
            transform: translateY(-1px);
        }

        .btn-primary {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            border-color: #3b82f6;
            color: white;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        .btn-primary:hover {
            background: linear-gradient(135deg, #1d4ed8, #1e40af);
        }

        /* Navigation Tabs */
        .tab-bar {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
            overflow-x: auto;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 0.95rem;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }

        .tab-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.04);
        }

        .tab-btn.active {
            color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.1);
            border-bottom: 2px solid var(--accent-cyan);
        }

        /* Bento Grid Layout */
        .bento-grid {
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }

        .bento-card {
            background: var(--surface);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 22px;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }

        .bento-card:hover {
            border-color: var(--border-hover);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }

        /* Top Metric Cards */
        .col-3 { grid-column: span 3; }
        .col-4 { grid-column: span 4; }
        .col-6 { grid-column: span 6; }
        .col-8 { grid-column: span 8; }
        .col-12 { grid-column: span 12; }

        @media (max-width: 1024px) {
            .col-3, .col-4 { grid-column: span 6; }
            .col-8 { grid-column: span 12; }
        }

        @media (max-width: 768px) {
            .col-3, .col-4, .col-6, .col-8 { grid-column: span 12; }
        }

        .metric-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 6px;
        }

        .metric-value {
            font-size: 2.2rem;
            font-weight: 800;
            line-height: 1.1;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .metric-sub {
            font-size: 0.85rem;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }

        /* Status Pills */
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .pill-cyan { background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); border: 1px solid rgba(6, 182, 212, 0.3); }
        .pill-emerald { background: rgba(16, 185, 129, 0.15); color: var(--accent-emerald); border: 1px solid rgba(16, 185, 129, 0.3); }
        .pill-violet { background: rgba(139, 92, 246, 0.15); color: var(--accent-violet); border: 1px solid rgba(139, 92, 246, 0.3); }
        .pill-amber { background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.3); }
        .pill-rose { background: rgba(244, 63, 94, 0.15); color: var(--accent-rose); border: 1px solid rgba(244, 63, 94, 0.3); }

        /* Kanban Board Style Script Canvas */
        .kanban-board {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
            margin-top: 10px;
        }

        .kanban-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            position: relative;
            transition: all 0.2s ease;
        }

        .kanban-card:hover {
            border-color: rgba(6, 182, 212, 0.4);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }

        .scene-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
        }

        .scene-badge {
            font-weight: 700;
            font-size: 0.85rem;
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .scene-timecode {
            font-family: monospace;
            font-size: 0.8rem;
            background: rgba(255, 255, 255, 0.06);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--text-secondary);
        }

        .editable-field {
            outline: none;
            border: 1px dashed transparent;
            padding: 4px 6px;
            border-radius: 4px;
            transition: all 0.2s;
        }

        .editable-field:hover, .editable-field:focus {
            border-color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.05);
        }

        .scene-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .visual-cue-box {
            background: rgba(139, 92, 246, 0.08);
            border-left: 3px solid var(--accent-violet);
            padding: 8px 12px;
            border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
            font-size: 0.85rem;
            color: #d8b4fe;
        }

        .keywords-cloud {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }

        .keyword-tag {
            background: rgba(6, 182, 212, 0.12);
            border: 1px solid rgba(6, 182, 212, 0.25);
            color: var(--accent-cyan);
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 9999px;
            cursor: pointer;
        }

        .talking-points-list {
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .talking-points-list li {
            font-size: 0.88rem;
            color: var(--text-secondary);
            position: relative;
            padding-left: 18px;
        }

        .talking-points-list li::before {
            content: "•";
            position: absolute;
            left: 4px;
            color: var(--accent-cyan);
            font-weight: bold;
        }

        /* Dossier Table & Explorer */
        .filter-bar {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }

        .search-box {
            flex: 1;
            min-width: 250px;
            position: relative;
        }

        .search-box input {
            width: 100%;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 10px 16px;
            border-radius: var(--radius-sm);
            font-size: 0.9rem;
            outline: none;
            transition: all 0.2s;
        }

        .search-box input:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.2);
        }

        .filter-chips {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }

        .chip-btn {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 0.8rem;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 9999px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .chip-btn:hover {
            background: var(--surface-hover);
            color: var(--text-primary);
        }

        .chip-btn.active {
            background: var(--accent-blue);
            color: white;
            border-color: var(--accent-blue);
        }

        .findings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 18px;
        }

        .finding-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            transition: all 0.2s;
        }

        .finding-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
        }

        .finding-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .finding-title {
            font-size: 1rem;
            font-weight: 700;
            color: var(--text-primary);
            text-decoration: none;
            display: inline-block;
        }

        .finding-title:hover {
            color: var(--accent-cyan);
        }

        .finding-summary {
            font-size: 0.85rem;
            color: var(--text-secondary);
            display: -webkit-box;
            -webkit-line-clamp: 4;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        /* Placeholders / Asset Pipeline Cards */
        .pipeline-stepper {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-top: 14px;
        }

        .pipeline-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .pipeline-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .status-ready { background: var(--accent-emerald); box-shadow: 0 0 8px var(--accent-emerald); }
        .status-pending { background: var(--accent-amber); box-shadow: 0 0 8px var(--accent-amber); }

        /* Code block & Previews */
        pre {
            background: #040711;
            padding: 16px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            overflow-x: auto;
            font-family: Consolas, Monaco, "Andale Mono", monospace;
            font-size: 0.85rem;
            color: #cbd5e1;
            line-height: 1.6;
        }

        .hidden {
            display: none !important;
        }
    </style>
</head>
<body>

    <!-- Header Section -->
    <header>
        <div class="brand">
            <span class="brand-badge">BENTO REPORT</span>
            <div>
                <h1 class="topic-title">__ROOT_TOPIC__</h1>
                <div style="font-size: 0.85rem; color: var(--text-muted);">
                    Autonomous Research Dossier • Generated __CREATED_AT__
                </div>
            </div>
        </div>
        <div class="header-actions">
            <button class="btn btn-primary" onclick="downloadEditedScript()">
                <span>💾 Export Edited Script</span>
            </button>
            <button class="btn" onclick="copyFullNarration()">
                <span>📋 Copy Narration</span>
            </button>
            <button class="btn" onclick="downloadJSONDossier()">
                <span>📥 Export JSON Dossier</span>
            </button>
        </div>
    </header>

    <!-- Top Bento Metrics Row -->
    <section class="bento-grid">
        <div class="bento-card col-3">
            <div class="metric-title">Total Sources Analyzed</div>
            <div class="metric-value">__TOTAL_SOURCES__</div>
            <div class="metric-sub">
                <span class="pill pill-cyan">Wikipedia</span>
                <span class="pill pill-rose">arXiv</span>
                <span class="pill pill-violet">GitHub</span>
                <span class="pill pill-amber">HN</span>
            </div>
        </div>

        <div class="bento-card col-3">
            <div class="metric-title">Rabbit-Hole Depth & Branches</div>
            <div class="metric-value">__BRANCHES_COUNT__ Branches</div>
            <div class="metric-sub">
                <span class="pill pill-emerald">Recursive Depth 1</span>
                <span>Deduplicated</span>
            </div>
        </div>

        <div class="bento-card col-3">
            <div class="metric-title">Estimated Video Runtime</div>
            <div class="metric-value" id="runtime-estimate">~06:30</div>
            <div class="metric-sub">
                <span id="word-count">~900 Words</span> • 140 WPM pace
            </div>
        </div>

        <div class="bento-card col-3">
            <div class="metric-title">Pipeline Asset Status</div>
            <div class="metric-value" style="font-size: 1.6rem; margin-top: 6px;">Ready for Render</div>
            <div class="metric-sub">
                <span class="pill pill-emerald">Dossier ✅</span>
                <span class="pill pill-emerald">Script ✅</span>
                <span class="pill pill-amber">Video ⏳</span>
            </div>
        </div>

        <!-- Executive Summary Banner -->
        <div class="bento-card col-12" style="background: linear-gradient(180deg, rgba(30, 41, 59, 0.7), var(--surface));">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h3 style="font-size: 1.1rem; font-weight: 700; color: var(--accent-cyan);">🌟 Executive Synthesis</h3>
                <span class="pill pill-cyan">Stitched Multi-Agent Knowledge</span>
            </div>
            <p style="color: var(--text-secondary); font-size: 0.95rem; line-height: 1.6;">
                __EXECUTIVE_SUMMARY__
            </p>
        </div>
    </section>

    <!-- Tab Navigation -->
    <nav class="tab-bar">
        <button class="tab-btn active" onclick="switchTab('canvas-tab', this)">🎬 Script Canvas (Kanban Board)</button>
        <button class="tab-btn" onclick="switchTab('dossier-tab', this)">🐇 Rabbit-Hole Dossier Explorer</button>
        <button class="tab-btn" onclick="switchTab('pipeline-tab', this)">📁 Asset Pipeline & File Placeholders</button>
        <button class="tab-btn" onclick="switchTab('takeaways-tab', this)">💡 Key Facts & Engineering Insights</button>
        <button class="tab-btn" onclick="switchTab('raw-tab', this)">📄 Raw JSON Dossier</button>
    </nav>

    <!-- TAB 1: SCRIPT CANVAS (KANBAN) -->
    <main id="canvas-tab" class="tab-content">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <div>
                <h2 style="font-size: 1.3rem;">Video Production Script Canvas</h2>
                <p style="font-size: 0.85rem; color: var(--text-muted);">
                    Click any scene title, talking point, or timecode to edit in-place. Changes auto-save locally.
                </p>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn" onclick="addNewScene()">➕ Add Scene</button>
                <button class="btn" onclick="resetScriptCanvas()">🔄 Reset Canvas</button>
            </div>
        </div>

        <div class="kanban-board" id="kanban-container">
            <!-- Scene Cards dynamically rendered from JSON -->
        </div>
    </main>

    <!-- TAB 2: DOSSIER EXPLORER -->
    <section id="dossier-tab" class="tab-content hidden">
        <div class="filter-bar">
            <div class="search-box">
                <input type="text" id="source-search" placeholder="Search 90+ research findings, keywords, URLs..." oninput="filterFindings()">
            </div>
            <div class="filter-chips">
                <button class="chip-btn active" onclick="filterBySource('all', this)">All Sources</button>
                <button class="chip-btn" onclick="filterBySource('wikipedia', this)">Wikipedia</button>
                <button class="chip-btn" onclick="filterBySource('arxiv', this)">arXiv</button>
                <button class="chip-btn" onclick="filterBySource('github', this)">GitHub</button>
                <button class="chip-btn" onclick="filterBySource('hackernews', this)">HackerNews</button>
                <button class="chip-btn" onclick="filterBySource('duckduckgo', this)">DuckDuckGo</button>
                <button class="chip-btn" onclick="filterBySource('youtube', this)">YouTube</button>
            </div>
        </div>

        <div class="findings-grid" id="findings-container">
            <!-- Source findings dynamically injected -->
        </div>
    </section>

    <!-- TAB 3: PIPELINE ASSET PLACEHOLDERS -->
    <section id="pipeline-tab" class="tab-content hidden">
        <h2 style="font-size: 1.3rem; margin-bottom: 8px;">Asset Pipeline & File Data Types</h2>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 20px;">
            Status of all data files and video media required for production:
        </p>

        <div class="pipeline-stepper">
            <div class="pipeline-card">
                <div class="pipeline-status">
                    <span class="status-dot status-ready"></span>
                    <span style="color: var(--accent-emerald);">DATA READY</span>
                </div>
                <div style="font-weight: 700; font-size: 0.95rem;">Research Dossier</div>
                <div style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">output/__SAFE_TOPIC___dossier.json</div>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Full hierarchical schema containing root topic, depth branches, entities, and sources.
                </p>
                <span class="pill pill-cyan">JSON Schema</span>
            </div>

            <div class="pipeline-card">
                <div class="pipeline-status">
                    <span class="status-dot status-ready"></span>
                    <span style="color: var(--accent-emerald);">REPORT READY</span>
                </div>
                <div style="font-weight: 700; font-size: 0.95rem;">Markdown Dossier</div>
                <div style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">output/__SAFE_TOPIC___research_report.md</div>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Publication-grade markdown report ready for archival or distribution.
                </p>
                <span class="pill pill-emerald">Markdown</span>
            </div>

            <div class="pipeline-card">
                <div class="pipeline-status">
                    <span class="status-dot status-ready"></span>
                    <span style="color: var(--accent-emerald);">SCRIPT READY</span>
                </div>
                <div style="font-weight: 700; font-size: 0.95rem;">Narration Script</div>
                <div style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">output/__SAFE_TOPIC___script.txt</div>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Timecoded script ready for TTS synthesis or voiceover recording.
                </p>
                <span class="pill pill-violet">Plain Text</span>
            </div>

            <div class="pipeline-card">
                <div class="pipeline-status">
                    <span class="status-dot status-pending"></span>
                    <span style="color: var(--accent-amber);">AUDIO PLACEHOLDER</span>
                </div>
                <div style="font-weight: 700; font-size: 0.95rem;">Voiceover Audio</div>
                <div style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">output/__SAFE_TOPIC___voiceover.mp3</div>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Generated via Silero TTS or gTTS using the synthesized script.
                </p>
                <span class="pill pill-amber">MP3 / WAV Audio</span>
            </div>

            <div class="pipeline-card">
                <div class="pipeline-status">
                    <span class="status-dot status-pending"></span>
                    <span style="color: var(--accent-amber);">VIDEO PLACEHOLDER</span>
                </div>
                <div style="font-weight: 700; font-size: 0.95rem;">Screen Recording / B-Roll</div>
                <div style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">raw/*.mp4 or segregated/b-roll/*.mp4</div>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Visual footage ingested and sanitized via video-tui.py.
                </p>
                <span class="pill pill-amber">MP4 Video</span>
            </div>

            <div class="pipeline-card">
                <div class="pipeline-status">
                    <span class="status-dot status-pending"></span>
                    <span style="color: var(--accent-amber);">FINAL RENDER</span>
                </div>
                <div style="font-weight: 700; font-size: 0.95rem;">Final Produced Video</div>
                <div style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">output/__SAFE_TOPIC___final.mp4</div>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Auto-edited by editor.py with keyword camera zooms, SFX on silences, and burned subtitles.
                </p>
                <span class="pill pill-rose">H.264 / AAC</span>
            </div>
        </div>
    </section>

    <!-- TAB 4: KEY TAKEAWAYS -->
    <section id="takeaways-tab" class="tab-content hidden">
        <h2 style="font-size: 1.3rem; margin-bottom: 12px;">Key Engineering Takeaways</h2>
        <div class="bento-grid">
            <div class="bento-card col-12">
                <ul id="takeaways-list" style="list-style: none; display: flex; flex-direction: column; gap: 14px;">
                    <!-- Takeaways injected here -->
                </ul>
            </div>
        </div>
    </section>

    <!-- TAB 5: RAW JSON -->
    <section id="raw-tab" class="tab-content hidden">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h2 style="font-size: 1.3rem;">Raw Structured JSON Dossier</h2>
            <button class="btn" onclick="navigator.clipboard.writeText(JSON.stringify(dossierData, null, 2))">📋 Copy Raw JSON</button>
        </div>
        <pre><code id="raw-json-viewer"></code></pre>
    </section>

    <!-- Embedded Dossier Data -->
    <script id="dossier-data" type="application/json">
__DOSSIER_JSON__
    </script>

    <script>
        const dossierData = JSON.parse(document.getElementById('dossier-data').textContent);
        let activeSourceFilter = 'all';
        let scriptScenes = JSON.parse(localStorage.getItem('script_' + dossierData.root_topic)) || dossierData.script_outline;

        // Initialize view
        document.addEventListener('DOMContentLoaded', () => {
            renderKanbanScenes();
            renderFindings();
            renderTakeaways();
            updateMetrics();
            document.getElementById('raw-json-viewer').textContent = JSON.stringify(dossierData, null, 2);
        });

        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.remove('hidden');
            btn.classList.add('active');
        }

        function renderKanbanScenes() {
            const container = document.getElementById('kanban-container');
            container.innerHTML = '';

            scriptScenes.forEach((scene, idx) => {
                const card = document.createElement('div');
                card.className = 'kanban-card';

                const keywordsHtml = (scene.keywords || []).map(kw => 
                    `<span class="keyword-tag" onclick="removeKeyword(${idx}, '${kw}')">${kw} ✕</span>`
                ).join('');

                const pointsHtml = (scene.talking_points || []).map((pt, pIdx) => 
                    `<li class="editable-field" contenteditable="true" onblur="updatePoint(${idx}, ${pIdx}, this.innerText)">${pt}</li>`
                ).join('');

                card.innerHTML = `
                    <div class="scene-header">
                        <div class="scene-badge">
                            <span>🎬 SCENE ${scene.scene_number || idx + 1}</span>
                        </div>
                        <span class="scene-timecode editable-field" contenteditable="true" onblur="updateSceneDuration(${idx}, this.innerText)">${scene.est_duration}</span>
                    </div>

                    <div class="scene-title editable-field" contenteditable="true" onblur="updateSceneTitle(${idx}, this.innerText)">
                        ${scene.section}
                    </div>

                    <div class="visual-cue-box">
                        <div style="font-size: 0.75rem; text-transform: uppercase; font-weight: bold; margin-bottom: 2px;">👁️ Camera Cue</div>
                        <div class="editable-field" contenteditable="true" onblur="updateVisualCue(${idx}, this.innerText)">
                            ${scene.visual_cue}
                        </div>
                    </div>

                    <div>
                        <div style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;">⚡ Auto-VFX Zoom Keywords</div>
                        <div class="keywords-cloud" id="keywords-${idx}">
                            ${keywordsHtml}
                            <span class="keyword-tag" style="background: rgba(255,255,255,0.08); border-color: var(--border);" onclick="addKeyword(${idx})">+ Add</span>
                        </div>
                    </div>

                    <div>
                        <div style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;">🎙️ Narration & Talking Points</div>
                        <ul class="talking-points-list" id="points-${idx}">
                            ${pointsHtml}
                        </ul>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        function updateSceneTitle(idx, text) {
            scriptScenes[idx].section = text.trim();
            saveLocalScript();
        }

        function updateSceneDuration(idx, text) {
            scriptScenes[idx].est_duration = text.trim();
            saveLocalScript();
        }

        function updateVisualCue(idx, text) {
            scriptScenes[idx].visual_cue = text.trim();
            saveLocalScript();
        }

        function updatePoint(sIdx, pIdx, text) {
            scriptScenes[sIdx].talking_points[pIdx] = text.trim();
            saveLocalScript();
            updateMetrics();
        }

        function addKeyword(sceneIdx) {
            const kw = prompt("Enter trigger keyword for Auto-VFX Zoom:");
            if (kw && kw.trim()) {
                if (!scriptScenes[sceneIdx].keywords) scriptScenes[sceneIdx].keywords = [];
                scriptScenes[sceneIdx].keywords.push(kw.trim());
                saveLocalScript();
                renderKanbanScenes();
            }
        }

        function removeKeyword(sceneIdx, keyword) {
            scriptScenes[sceneIdx].keywords = scriptScenes[sceneIdx].keywords.filter(k => k !== keyword);
            saveLocalScript();
            renderKanbanScenes();
        }

        function addNewScene() {
            const newNum = scriptScenes.length + 1;
            scriptScenes.push({
                scene_number: newNum,
                section: `New Scene: Topic Exploration`,
                est_duration: `0${newNum}:00 - 0${newNum}:45`,
                visual_cue: `Screen capture or architecture diagram`,
                talking_points: [`Present key technical insight and practical demo.`],
                keywords: [`important`, `explore`]
            });
            saveLocalScript();
            renderKanbanScenes();
            updateMetrics();
        }

        function resetScriptCanvas() {
            if (confirm("Reset canvas to original generated script?")) {
                localStorage.removeItem('script_' + dossierData.root_topic);
                scriptScenes = JSON.parse(JSON.stringify(dossierData.script_outline));
                renderKanbanScenes();
                updateMetrics();
            }
        }

        function saveLocalScript() {
            localStorage.setItem('script_' + dossierData.root_topic, JSON.stringify(scriptScenes));
        }

        function updateMetrics() {
            let totalWords = 0;
            scriptScenes.forEach(s => {
                (s.talking_points || []).forEach(pt => {
                    totalWords += pt.split(/\\s+/).filter(Boolean).length;
                });
            });

            const totalSeconds = Math.round((totalWords / 140) * 60);
            const mins = Math.floor(totalSeconds / 60);
            const secs = totalSeconds % 60;

            document.getElementById('word-count').innerText = `~${totalWords} Words`;
            document.getElementById('runtime-estimate').innerText = `~${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }

        function renderTakeaways() {
            const list = document.getElementById('takeaways-list');
            if (!list) return;
            list.innerHTML = '';
            (dossierData.key_takeaways || []).forEach(t => {
                const li = document.createElement('li');
                li.style.cssText = 'font-size: 1rem; color: var(--text-secondary); display: flex; gap: 10px; align-items: flex-start;';
                li.innerHTML = `<span style="color: var(--accent-cyan); font-weight: bold;">✔</span><span>${t}</span>`;
                list.appendChild(li);
            });
        }

        function renderFindings() {
            const container = document.getElementById('findings-container');
            const query = (document.getElementById('source-search')?.value || '').toLowerCase();
            container.innerHTML = '';

            const sources = dossierData.sources || [];
            const filtered = sources.filter(s => {
                const matchesType = activeSourceFilter === 'all' || s.source_type.toLowerCase() === activeSourceFilter.toLowerCase();
                const matchesQuery = !query || 
                    s.title.toLowerCase().includes(query) || 
                    s.summary.toLowerCase().includes(query) || 
                    (s.source && s.source.toLowerCase().includes(query));
                return matchesType && matchesQuery;
            });

            filtered.forEach(item => {
                const card = document.createElement('div');
                card.className = 'finding-card';

                let badgeClass = 'pill-cyan';
                if (item.source_type === 'arxiv') badgeClass = 'pill-rose';
                else if (item.source_type === 'github') badgeClass = 'pill-violet';
                else if (item.source_type === 'hackernews') badgeClass = 'pill-amber';
                else if (item.source_type === 'youtube') badgeClass = 'pill-rose';
                else if (item.source_type === 'duckduckgo') badgeClass = 'pill-emerald';

                card.innerHTML = `
                    <div class="finding-meta">
                        <span class="pill ${badgeClass}">${item.source}</span>
                        <span style="font-size: 0.75rem; color: var(--text-muted);">${item.topic || 'Root'}</span>
                    </div>
                    <a href="${item.url}" target="_blank" class="finding-title">
                        ${item.title} ↗
                    </a>
                    <p class="finding-summary">${item.summary}</p>
                    <div style="margin-top: auto; padding-top: 8px;">
                        <a href="${item.url}" target="_blank" class="btn" style="padding: 4px 8px; font-size: 0.75rem;">Open Source ↗</a>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        function filterBySource(type, btn) {
            activeSourceFilter = type;
            document.querySelectorAll('.chip-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderFindings();
        }

        function filterFindings() {
            renderFindings();
        }

        function downloadEditedScript() {
            let content = `# Video Script: ${dossierData.root_topic}\\n\\n`;
            content += `## Executive Hook\\n${dossierData.executive_summary}\\n\\n`;

            scriptScenes.forEach(scene => {
                content += `## Scene ${scene.scene_number}: ${scene.section} (${scene.est_duration})\\n`;
                content += `Visual Cue: [${scene.visual_cue}]\\n`;
                content += `Trigger Keywords: [${(scene.keywords || []).join(', ')}]\\n`;
                (scene.talking_points || []).forEach(pt => {
                    content += `- ${pt}\\n`;
                });
                content += `\\n`;
            });

            const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${dossierData.root_topic.replace(/\\s+/g, '_').toLowerCase()}_script_edited.txt`;
            a.click();
        }

        function copyFullNarration() {
            let narration = '';
            scriptScenes.forEach(scene => {
                narration += `${scene.section}:\\n`;
                (scene.talking_points || []).forEach(pt => {
                    narration += `${pt} `;
                });
                narration += `\\n\\n`;
            });

            navigator.clipboard.writeText(narration).then(() => {
                alert("Narration text copied to clipboard!");
            });
        }

        function downloadJSONDossier() {
            const blob = new Blob([JSON.stringify(dossierData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${dossierData.root_topic.replace(/\\s+/g, '_').toLowerCase()}_dossier.json`;
            a.click();
        }
    </script>
</body>
</html>
"""


def generate_html_dashboard(dossier: ResearchDossier, output_path: Optional[str] = None) -> str:
    """
    Generate an interactive, modern HTML report with Bento Grid and Kanban Script Canvas.
    """
    safe_topic = dossier.root_topic.replace(" ", "_").lower()
    if output_path is None:
        output_file = Path("output") / f"{safe_topic}_dashboard.html"
    else:
        output_file = Path(output_path)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    dossier_dict = dossier.to_dict()
    dossier_json = json.dumps(dossier_dict, ensure_ascii=False)

    rendered = (
        HTML_TEMPLATE
        .replace("__ROOT_TOPIC__", str(dossier.root_topic))
        .replace("__SAFE_TOPIC__", str(safe_topic))
        .replace("__CREATED_AT__", str(dossier.created_at))
        .replace("__TOTAL_SOURCES__", str(dossier.total_sources))
        .replace("__BRANCHES_COUNT__", str(len(dossier.tree.sub_branches)))
        .replace("__EXECUTIVE_SUMMARY__", str(dossier.executive_summary))
        .replace("__DOSSIER_JSON__", dossier_json)
    )

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered)

    return str(output_file)


def main():
    import sys
    from ..core.models import ResearchDossier, BranchNode, ResearchItem

    if len(sys.argv) < 2:
        print("Usage: python -m content_machine.ui.dashboard <dossier.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: file not found: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Reconstruct ResearchDossier
    def parse_node(d):
        return BranchNode(
            topic=d.get("topic", ""),
            depth=d.get("depth", 0),
            parent_topic=d.get("parent_topic"),
            summary=d.get("summary", ""),
            keywords=d.get("keywords", []),
            findings=[
                ResearchItem(
                    topic=f.get("topic", d.get("topic", "")),
                    source_type=f.get("source_type", "web"),
                    title=f.get("title", ""),
                    url=f.get("url", ""),
                    summary=f.get("summary", ""),
                    key_facts=f.get("key_facts", []),
                    entities=f.get("entities", [])
                )
                for f in d.get("findings", [])
            ],
            sub_branches=[parse_node(sub) for sub in d.get("sub_branches", [])]
        )

    tree = parse_node(data.get("tree", {}))
    all_findings = [
        ResearchItem(
            topic=s.get("topic", data.get("root_topic", "")),
            source_type=s.get("source_type", "web"),
            title=s.get("title", ""),
            url=s.get("url", ""),
            summary=s.get("summary", ""),
            source=s.get("source", s.get("source_type", "web")),
            depth=s.get("depth", 0)
        )
        for s in data.get("sources", [])
    ]

    dossier = ResearchDossier(
        root_topic=data.get("root_topic", "research"),
        created_at=data.get("created_at", ""),
        total_sources=data.get("total_sources", len(all_findings)),
        tree=tree,
        all_findings=all_findings,
        executive_summary=data.get("executive_summary", ""),
        key_takeaways=data.get("key_takeaways", []),
        script_outline=data.get("script_outline", [])
    )

    out_file = generate_html_dashboard(dossier)
    print(f"✅ Interactive Modern Bento Grid Dashboard generated at: {out_file}")


if __name__ == "__main__":
    main()
