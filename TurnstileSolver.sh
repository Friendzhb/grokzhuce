#!/usr/bin/env bash
# Turnstile Solver 启动脚本（Linux / macOS 服务器）
# 默认以无头（headless）模式运行，无需图形界面。
# 用法:
#   bash TurnstileSolver.sh               # 默认 5 线程，headless
#   bash TurnstileSolver.sh --thread 8    # 指定线程数
#   bash TurnstileSolver.sh --no-headless # 本地调试时启用 GUI（需图形界面）
python api_solver.py --browser_type camoufox --thread 5 --debug "$@"
