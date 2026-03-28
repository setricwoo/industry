"""
extract_summaries.py - 从PDF中提取各行业的历史总结
运行: python extract_summaries.py
输出: summaries.js
"""
import fitz  # PyMuPDF
import os
import re
import json
from pathlib import Path
from datetime import datetime

# 行业名称（PDF中的标题）
INDUSTRY_NAMES = ['煤炭', '黑色', '有色', '石化', '基础化工']
INDUSTRY_MAP = {'黑色': '钢铁'}  # PDF中用"黑色"，统一映射为"钢铁"

# 通过内容关键词识别行业
INDUSTRY_KEYWORDS = {
    '煤炭': ['秦港', '动力煤', '秦皇岛', '电厂库存', '日耗', '煤炭'],
    '钢铁': ['螺纹', '热卷', '高炉', '铁水', '五大材', '钢材'],
    '有色': ['铜', '铝', '电解铝', '铜精矿', 'TC', 'RC', '伦敦金'],
    '石化': ['布伦特', '原油', '天然气', 'NYMEX', '炼厂开工', '裂解价差'],
    '基础化工': ['PTA', '涤纶', 'POY', 'FDY', 'DTY', '化工产品价格指数', '乙烯']
}


def extract_date_from_filename(filename):
    """从文件名提取日期"""
    match = re.search(r'(\d{8})', filename)
    if match:
        date_str = match.group(1)
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return None


def detect_industry_from_content(text):
    """通过内容关键词识别行业"""
    scores = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[industry] = score

    if scores:
        return max(scores, key=scores.get)
    return None


def format_summary_with_breaks(text):
    """格式化总结文本，在1）2）3）处添加换行，保留段落分隔"""
    # 在数字+）前面添加换行（如果前面不是换行）
    text = re.sub(r'(?<!\n)(\d+）)', r'\n\1', text)
    # 清理多余的空格，但保留换行
    text = re.sub(r'[^\S\n]+', ' ', text)
    # 清理开头的空白
    text = text.strip()
    return text


def extract_summaries_from_pdf(pdf_path):
    """从单个PDF提取各行业总结"""
    doc = fitz.open(pdf_path)
    summaries = {}
    found_industries = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        # 保留空行用于检测段落分隔
        lines = [l.strip() for l in text.split('\n')]

        if not lines:
            continue

        first_line = lines[0]
        industry = None

        # 方法1：第一行是明确的行业标题
        if first_line in INDUSTRY_NAMES:
            industry = INDUSTRY_MAP.get(first_line, first_line)

        # 方法2：第一行包含行业标题
        elif any(name in first_line for name in INDUSTRY_NAMES):
            for name in INDUSTRY_NAMES:
                if name in first_line:
                    industry = INDUSTRY_MAP.get(name, name)
                    break

        # 方法3：通过内容关键词识别（针对没有标题的页面）
        else:
            # 检查是否是表格页（跳过）
            if first_line in ['项目', '指标', '单位']:
                continue
            # 检查前几行内容是否像总结段落
            content = ' '.join(lines[:5])
            if '本周' in content or '价格方面' in content:
                detected = detect_industry_from_content(content)
                if detected and detected not in found_industries:
                    industry = detected

        if industry and industry not in found_industries:
            # 收集该行业的总结段落
            summary_parts = []
            prev_was_empty = False
            for line in lines[1:] if first_line in INDUSTRY_NAMES or any(name in first_line for name in INDUSTRY_NAMES) else lines:
                # 遇到图表或资料来源则停止
                if line.startswith('图表') or line.startswith('资料来源') or line.startswith('表'):
                    break
                # 跳过页码
                if line.isdigit():
                    continue
                # 跳过表格表头
                if line in ['项目', '指标', '单位', '最新值']:
                    break

                # 检查是否是空行（段落分隔）
                stripped = line.strip()
                if not stripped:
                    if summary_parts and not prev_was_empty:
                        summary_parts.append('\n\n')  # 插入段落分隔
                        prev_was_empty = True
                    continue

                summary_parts.append(stripped)
                prev_was_empty = False

            summary_text = ''.join(summary_parts)
            if summary_text and len(summary_text) > 20:  # 过滤太短的内容
                summaries[industry] = format_summary_with_breaks(summary_text)
                found_industries.add(industry)

    doc.close()
    return summaries


def main():
    # 获取所有PDF文件
    pdf_dir = Path(__file__).parent
    pdf_files = sorted(pdf_dir.glob('周期行业周度跟踪*.pdf'), reverse=True)

    print(f"找到 {len(pdf_files)} 个PDF文件")

    # 收集所有总结
    all_dates = []
    all_summaries = {industry: {} for industry in ['煤炭', '钢铁', '有色', '石化', '基础化工']}

    for pdf_file in pdf_files:
        date = extract_date_from_filename(pdf_file.name)
        if not date:
            print(f"无法提取日期: {pdf_file.name}")
            continue

        print(f"处理: {pdf_file.name} -> {date}")
        all_dates.append(date)

        try:
            summaries = extract_summaries_from_pdf(str(pdf_file))
            for industry, summary in summaries.items():
                if industry in all_summaries:
                    all_summaries[industry][date] = summary
                    print(f"  {industry}: {len(summary)} 字符")
        except Exception as e:
            print(f"  错误: {e}")

    # 按日期倒序排列
    all_dates.sort(reverse=True)

    # 读取现有的总览内容（保留用户手动添加的内容）
    existing_overview = {}
    existing_js_path = pdf_dir / 'summaries.js'
    if existing_js_path.exists():
        with open(existing_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 提取现有的overview内容
            match = re.search(r'overview:\s*\{([^}]+)\}', content, re.DOTALL)
            if match:
                overview_content = match.group(1)
                # 提取所有日期和内容
                for m in re.finditer(r'"(\d{4}-\d{2}-\d{2})":\s*"([^"]*)"', overview_content):
                    existing_overview[m.group(1)] = m.group(2)

    # 生成 JavaScript 文件
    js_content = f"""// 行业历史总结数据
// 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// 共 {len(all_dates)} 期报告

const HISTORICAL_SUMMARIES = {{
    dates: {json.dumps(all_dates, ensure_ascii=False, indent=4)},

    // 市场总览（手动更新）
    overview: {{
"""

    # 保留现有的总览内容
    for date, summary in sorted(existing_overview.items(), reverse=True):
        js_content += f'        "{date}": "{summary}",\n'

    js_content += """    },

    // 各行业观点（从PDF自动提取）
    summaries: {
"""

    for industry in ['煤炭', '钢铁', '有色', '石化', '基础化工']:
        js_content += f"        '{industry}': {{\n"
        for date in all_dates:
            summary = all_summaries[industry].get(date, '')
            if summary:
                # 转义引号和反斜杠
                summary_escaped = summary.replace('\\', '\\\\').replace('"', '\\"')
                # 保留换行符（转义为\n）
                summary_escaped = summary_escaped.replace('\n', '\\n')
                js_content += f'            "{date}": "{summary_escaped}",\n'
        js_content += "        },\n"

    js_content += """    }
};
"""

    output_path = pdf_dir / 'summaries.js'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)

    print(f"\n已生成: {output_path}")
    print(f"日期数: {len(all_dates)}")
    for industry in ['煤炭', '钢铁', '有色', '石化', '基础化工']:
        count = len(all_summaries[industry])
        print(f"  {industry}: {count} 条总结")


if __name__ == '__main__':
    main()
