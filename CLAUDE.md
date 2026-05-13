# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based test fixture software for manufacturing and testing equipment, specifically designed for Haier IoT devices. The application provides a GUI interface using wxPython for various testing scenarios including water testing, charging dock testing, collision detection, and more.

## Development Commands

### Environment Setup
- Create virtual environment: `python -m venv .venv`
- Activate virtual environment (PowerShell): `.\.venv\Scripts\Activate.ps1`
- Install dependencies: `pip install -r requirements.txt`
- Configure pip to use Tsinghua mirror: `pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`

### Running the Application
- Start the application: `python main.py`
- Build executable with PyInstaller: `pyinstaller --onefile main.py`

### Configuration
- Main configuration file: `config.yaml`
- Device types are configured via `device_type` parameter (e.g., "001" for water testing, "002" for charging dock testing)
- MES system integration controlled by `use_mes` setting

## Code Architecture

### Main Components
- **main.py**: Application entry point with wxPython GUI initialization
- **ui/MainFrame.py**: Main GUI window implementation
- **config.yaml**: Central configuration for device types, MES settings, and testing parameters
- **database/**: Database-related modules
- **mes/**: Manufacturing Execution System integration
- **myserial/**: Serial communication handling
- **tool_box/**: Utility functions and tools
- **test_tool/**: Testing-specific functionality

### Key Features
- Multi-device testing support through configurable device types
- MES system integration for manufacturing data management
- Serial communication for hardware interfacing
- Weight measurement support for weighing workstations
- Configurable testing schemes and parameters

### Dependencies
- wxPython 4.2.5 for GUI
- PySerial for serial communication
- OpenPyXL for Excel file handling
- Requests for HTTP communication with MES
- PyInstaller for executable packaging

## Configuration Management

The application uses `config.yaml` for all operational parameters:
- `device_type`: Determines which testing fixture logic to use
- `mcu_version`: Firmware version for testing validation
- `use_mes`: Controls MES system integration (1: Haier+Anker, 2: Haier only, 3: Anker only)
- `user_com`: Serial port configuration (empty for auto-detection)
- Weight measurement parameters for weighing workstations

## Build and Distribution

The project is configured for PyInstaller packaging with `main.spec` file. The build process creates a single executable for deployment on testing workstations.