# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DLP01 is a Python-based forum auto-download application for fastzone.org. It crawls forum posts, sends "thanks" to unlock hidden content, extracts download links (MEGA, Gofile, etc.), sends them to JDownloader, and auto-extracts downloaded archives.

## Commands

```bash
# Run GUI application
python dlp01_gui.py

# Run CLI with options
python src/main.py                    # Normal run
python src/main.py --dry-run          # Test without sending thanks/downloads
python src/main.py --schedule         # Scheduled mode (runs periodically)
python src/main.py --no-size-limit    # Ignore 2GB file size limit

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Core Components

- **`src/main.py`** - `DLP01` class: main orchestrator that coordinates crawling, thanks-sending, link extraction, and JDownloader integration
- **`dlp01_gui.py`** - PyQt6 GUI launcher, loads `src/gui/main_window.py`

### Module Structure

**Crawler** (`src/crawler/`)
- `forum_client.py` - HTTP client with cookie-based auth for forum requests
- `post_parser.py` - Parses forum HTML to extract post listings
- `thanks_handler.py` - Sends thanks to unlock hidden content
- `forum_searcher.py` - Section-based post search
- `forum_structure_scraper.py` - Scrapes forum section hierarchy

**Downloader** (`src/downloader/`)
- `link_extractor.py` - Regex-based extraction of download links (MEGA, Gofile, etc.) and passwords from post HTML
- `jd_integration.py` - Creates `.crawljob` files for JDownloader folderwatch
- `extract_monitor.py` - Monitors download directory, auto-extracts archives with WinRAR/UnRAR, handles nested archives, duplicate files, and file filtering
- `jd_history_reader.py` - Reads JDownloader history for password matching

**Database** (`src/database/`)
- `db_manager.py` - SQLite wrapper. Tables: `posts`, `downloads`, `run_history`, `download_history`, `forum_sections`, `search_results`

**GUI** (`src/gui/`)
- `main_window.py` - Main tabbed window
- `section_search_widget.py` / `section_manager_widget.py` - Forum section management
- `extract_history_widget.py` / `download_history_widget.py` - History views
- `extract_settings_widget.py` - Extraction settings

**Models** (`src/models/`)
- `extract_models.py` - Dataclasses: `ArchiveInfo`, `ExtractResult`, `ExtractConfig`, `FilterResult`, `DuplicateResult`, `FailureTracker`

### Key Data Flow

1. `ForumClient` fetches forum pages with authenticated session
2. `PostParser` extracts posts matching title filters (e.g., "MEGA@", "Gofile@HTTP")
3. `ThanksHandler` sends thanks to unlock hidden download links
4. `LinkExtractor` extracts download URLs and passwords from post HTML
5. `JDownloaderIntegration` creates `.crawljob` files in folderwatch directory
6. `ExtractMonitor` watches download directory, extracts archives using WinRAR

## Configuration

Main config: `config/config.yaml`

Key sections:
- `forum.target_sections` - Forum sections to crawl (by fid)
- `forum.title_filters` - Post title patterns to match
- `paths.download_dir` / `extract_dir` - Download and extraction directories
- `jdownloader.folderwatch_path` - JDownloader folderwatch directory
- `extract.*` - Extraction settings (nested depth, excluded extensions, smart folder logic)

Authentication: `config/cookies.json` - Browser-exported cookies for forum login

## Database

SQLite database at `data/dlp.db`. Key tables:
- `posts` - Tracked forum posts with thanks status
- `downloads` - Download links with extraction status
- `forum_sections` - Cached forum structure
- `search_results` - Temporary search session results

## Chinese Language

This is a Traditional Chinese project. UI text, logs, and comments are in Chinese. The forum (fastzone.org) is Chinese-language.
