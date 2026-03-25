#!/usr/bin/env python3
"""
合并零散的 JSON 文件到单个文件
"""
import json
import os
from pathlib import Path
from tqdm import tqdm
import argparse


def consolidate_directory(source_dir, output_file, delete_originals=False):
    """
    将目录中的所有 JSON 文件合并到一个文件中
    
    Args:
        source_dir: 源目录路径
        output_file: 输出文件路径
        delete_originals: 是否删除原始文件
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"❌ 目录不存在: {source_dir}")
        return
    
    # 收集所有 JSON 文件
    json_files = sorted(source_path.glob("*.json"))
    
    if not json_files:
        print(f"⚠️  目录中没有 JSON 文件: {source_dir}")
        return
    
    print(f"📂 处理目录: {source_dir}")
    print(f"📄 找到 {len(json_files)} 个 JSON 文件")
    
    # 合并所有 JSON 文件
    consolidated_data = []
    
    for json_file in tqdm(json_files, desc="合并文件"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 如果是单个对象，添加文件名作为 key
                if isinstance(data, dict):
                    data['_source_file'] = json_file.name
                consolidated_data.append(data)
        except Exception as e:
            print(f"⚠️  读取文件失败 {json_file}: {e}")
    
    # 写入合并后的文件
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(consolidated_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已合并到: {output_file}")
    print(f"📊 总计 {len(consolidated_data)} 条记录")
    
    # 计算文件大小
    original_size = sum(f.stat().st_size for f in json_files)
    new_size = output_path.stat().st_size
    print(f"💾 原始大小: {original_size / 1024 / 1024:.2f} MB")
    print(f"💾 合并后大小: {new_size / 1024 / 1024:.2f} MB")
    print(f"📉 压缩率: {(1 - new_size / original_size) * 100:.1f}%")
    
    # 删除原始文件
    if delete_originals:
        print("🗑️  删除原始文件...")
        for json_file in tqdm(json_files, desc="删除文件"):
            json_file.unlink()
        print("✅ 原始文件已删除")


def consolidate_nested_directories(base_dir, pattern="**/", delete_originals=False):
    """
    递归合并嵌套目录中的 JSON 文件
    
    Args:
        base_dir: 基础目录
        pattern: 目录匹配模式
        delete_originals: 是否删除原始文件
    """
    base_path = Path(base_dir)
    
    # 找到所有包含 JSON 文件的子目录
    subdirs = set()
    for json_file in base_path.rglob("*.json"):
        subdirs.add(json_file.parent)
    
    print(f"📂 找到 {len(subdirs)} 个包含 JSON 文件的目录")
    
    for subdir in sorted(subdirs):
        # 跳过已经是合并文件的目录
        json_files = list(subdir.glob("*.json"))
        if len(json_files) <= 1:
            continue
        
        # 生成输出文件名
        relative_path = subdir.relative_to(base_path)
        output_file = subdir / f"_consolidated_{relative_path.name}.json"
        
        consolidate_directory(subdir, output_file, delete_originals)
        print()


def main():
    parser = argparse.ArgumentParser(description="合并零散的 JSON 文件")
    parser.add_argument("source", help="源目录路径")
    parser.add_argument("-o", "--output", help="输出文件路径（单目录模式）")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument("-d", "--delete", action="store_true", help="删除原始文件")
    
    args = parser.parse_args()
    
    if args.recursive:
        consolidate_nested_directories(args.source, delete_originals=args.delete)
    else:
        if not args.output:
            source_path = Path(args.source)
            args.output = source_path.parent / f"{source_path.name}_consolidated.json"
        consolidate_directory(args.source, args.output, args.delete)


if __name__ == "__main__":
    main()
