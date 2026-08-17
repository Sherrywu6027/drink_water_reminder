#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康助手应用打包脚本
使用PyInstaller将Python应用打包成exe文件
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_pyinstaller():
    """检查PyInstaller是否已安装"""
    try:
        import PyInstaller
        print("✅ PyInstaller已安装")
        return True
    except ImportError:
        print("❌ PyInstaller未安装")
        return False

def install_pyinstaller():
    """安装PyInstaller"""
    print("正在安装PyInstaller...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✅ PyInstaller安装成功")
        return True
    except subprocess.CalledProcessError:
        print("❌ PyInstaller安装失败")
        return False

def create_icon():
    """创建应用图标（如果不存在）"""
    icon_path = "icon.ico"
    if not os.path.exists(icon_path):
        print("⚠️ 未找到图标文件，将使用默认图标")
        return None
    return icon_path

def build_app():
    """打包应用"""
    print("开始打包健康助手应用...")
    
    # 检查主程序文件
    main_file = "drink_water_reminder.py"
    if not os.path.exists(main_file):
        print(f"❌ 未找到主程序文件: {main_file}")
        return False
    
    # 创建图标
    icon_file = create_icon()
    
    # 构建PyInstaller命令
    cmd = [
        "pyinstaller",
        "--onefile",  # 打包成单个文件
        "--windowed",  # 不显示控制台窗口
        "--name=健康助手",  # 应用名称
        "--clean",  # 清理临时文件
        "--noconfirm",  # 不询问覆盖
    ]
    
    if icon_file:
        cmd.extend(["--icon", icon_file])
    
    # 添加数据文件
    cmd.extend([
        "--add-data", "*.json;.",  # 配置文件
        "--add-data", "*.md;.",    # 说明文档
    ])
    
    cmd.append(main_file)
    
    print("执行打包命令:", " ".join(cmd))
    
    try:
        subprocess.check_call(cmd)
        print("✅ 应用打包成功！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 打包失败: {e}")
        return False

def create_distribution():
    """创建发布包"""
    print("创建发布包...")
    
    # 创建发布目录
    dist_dir = "健康助手_发布版"
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)
    
    # 复制可执行文件
    exe_file = "dist/健康助手.exe"
    if os.path.exists(exe_file):
        shutil.copy2(exe_file, dist_dir)
        print(f"✅ 复制可执行文件: {exe_file}")
    else:
        print(f"❌ 未找到可执行文件: {exe_file}")
        return False
    
    # 复制配置文件（如果exe中没有包含）
    config_files = ["drink_data.json", "user_config.json", "reminder_settings.json"]
    for config_file in config_files:
        if os.path.exists(config_file):
            shutil.copy2(config_file, dist_dir)
            print(f"✅ 复制配置文件: {config_file}")
    
    # 创建说明文档
    readme_content = """# 健康助手

## 使用说明
1. 双击"健康助手.exe"启动程序
2. 首次运行会要求设置昵称
3. 在设置中可以调整提醒间隔和主题
4. 支持开机自启动和窗口置顶

## 功能特性
- 喝水、站立、护眼、运动提醒
- 自定义提醒间隔
- 主题颜色自定义
- 数据自动保存
- 开机自启动

## 注意事项
- 首次运行可能需要Windows安全提示，请选择"仍要运行"
- 建议将程序添加到杀毒软件白名单
- 数据文件保存在程序同目录下

## 技术支持
如有问题请联系开发者
"""
    
    with open(os.path.join(dist_dir, "使用说明.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print(f"✅ 发布包创建完成: {dist_dir}")
    return True

def main():
    """主函数"""
    print("=" * 50)
    print("健康助手应用打包工具")
    print("=" * 50)
    
    # 检查PyInstaller
    if not check_pyinstaller():
        if not install_pyinstaller():
            return
    
    # 打包应用
    if not build_app():
        return
    
    # 创建发布包
    if not create_distribution():
        return
    
    print("\n🎉 打包完成！")
    print("发布包位置: 健康助手_发布版/")
    print("可以将整个文件夹分享给其他用户使用")

if __name__ == "__main__":
    main() 