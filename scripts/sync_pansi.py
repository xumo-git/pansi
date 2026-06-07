#!/usr/bin/env python3
"""
盘丝洞 → pansi 自动同步脚本

用法:
  python3 scripts/sync_pansi.py          # 只预览差异
  python3 scripts/sync_pansi.py --sync   # 生成缺失章节 HTML
  python3 scripts/sync_pansi.py --push   # 推送至 GitHub
  python3 scripts/sync_pansi.py --sync --push  # 生成 + 推送
"""

import os, re, sys, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = Path("/Volumes/Mac1T/盘丝洞")

# ── 中文字符转换 ──
CN_DIGITS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
CN_TENS   = ["", "十", "二十", "三十", "四十", "五十", "六十", "七十", "八十", "九十"]

def _to_chinese(n: int) -> str:
    if n <= 9:
        return CN_DIGITS[n]
    t, d = divmod(n, 10)
    return (CN_TENS[t] + (CN_DIGITS[d] if d else "")).lstrip("零") or "零"

# ── 小说配置 ──
NOVELS = [
    {
        "id": "tianming59",
        "source_dir": SOURCE / "天命五九" / "小说",
        "target_dir": REPO / "tianming59",
        "prefix": "chapter-",
        "ext": ".html",
        "file_num": str,
        "parse_file": lambda fname: (
            int(re.match(r"第(\d+)章", fname).group(1)),
            fname.split("-", 1)[1].replace(".md", "")
        ),
        "label_num": lambda n: _to_chinese(n),
        "label_fmt": lambda num_str, title: f"— 第{num_str}章 —",
        "nav_title": "天命五九",
        "footer": '<span class="author">盘丝墨痕</span> · 天命五九 · 杏林春暖',
        "end_fmt": lambda num_str: f"天命五九 · 第{num_str}章",
        "html_title_fmt": lambda num_str, title: f"第{num_str}章 · {title} · 天命五九",
        "index_path": "index.html",
    },
    {
        "id": "xunxui",
        "source_dir": SOURCE / "蕊的故事" / "小说",
        "target_dir": REPO / "xunxui",
        "prefix": "chapter-",
        "ext": ".html",
        "file_num": str,
        "parse_file": lambda fname: (
            0 if fname.startswith("序章") else int(re.match(r"第(\d+)章", fname).group(1)),
            (fname.split("-", 1)[1] if "-" in fname else fname).replace(".md", "")
        ),
        "label_num": lambda n: str(n) if n > 0 else "序",
        "label_fmt": lambda num_str, title: f"— 序章 —" if num_str == "序" else f"— 第{num_str}章 —",
        "nav_title": "驯蕊",
        "footer": '<span class="author">驯蕊</span> · 盘丝墨痕',
        "end_fmt": lambda num_str: f"驯蕊 · {'' if num_str=='序' else '第'}{num_str}章",
        "html_title_fmt": lambda num_str, title: f"{title} · 驯蕊",
        "index_path": "index.html",
    },
    {
        "id": "yuantiang",
        "source_dir": SOURCE / "我真是袁天罡" / "小说",
        "target_dir": REPO / "yuantiang",
        "prefix": "ch",
        "ext": ".html",
        "file_num": lambda n: f"{n:02d}",
        "parse_file": lambda fname: (
            int(re.match(r"第(\d+)章", fname).group(1)),
            fname.split("-", 1)[1].replace(".md", "")
        ),
        "label_num": lambda n: f"{n:02d}",
        "label_fmt": lambda num_str, title: f"— 第{num_str}章 —",
        "nav_title": "我真是袁天罡",
        "footer": '<span class="author">我真是袁天罡</span> · 盘丝墨痕',
        "end_fmt": lambda num_str: f"我真是袁天罡 · 第{num_str}章",
        "html_title_fmt": lambda num_str, title: f"{title} · 我真是袁天罡",
        "index_path": "index.html",
    },
]

# ── Markdown → HTML ──
def md_to_html(md_text: str) -> str:
    """将正文 Markdown 转为 HTML（不含尾注/盘丝吐槽）。"""
    tail_re = re.compile(r"\n---\s*\n|\n<hr>\s*\n")
    m = tail_re.search(md_text)
    body = md_text[:m.start()] if m else md_text

    lines = body.split("\n")
    out = []
    para = []
    skip_title = True

    for line in lines:
        if line.startswith("# ") and skip_title:
            skip_title = False
            continue

        if line.startswith("## "):
            flush_para(para, out)
            out.append(f"<h2>{line.strip('# ').strip()}</h2>")
            continue

        if re.match(r"^</?(hr|p|div|strong|em|a|br|h[1-6])", line):
            flush_para(para, out)
            out.append(line)
            continue

        if re.search(r"[（(]第[\u4e00-\u9fff\d]+章完[）)]", line):
            flush_para(para, out)
            out.append(f"<p>\n{line.strip()}\n</p>")
            continue

        if not line.strip():
            flush_para(para, out)
            continue

        para.append(line)

    flush_para(para, out)
    return "\n".join(out)

def flush_para(para: list, out: list):
    if not para:
        return
    text = "\n".join(para)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    out.append(f"<p>\n{text}\n</p>" if not text.strip().startswith("<") else text)
    para.clear()

def extract_zh_title(md_text: str) -> str:
    m = re.search(r"^# .*?[··]\s*(.+?)\s*$", md_text, re.M)
    return m.group(1).strip() if m else ""

def extract_update_info(md_text: str) -> str:
    for line in md_text.split("\n"):
        raw = line.strip().strip("*_").strip()
        if re.search(r"更新于\s*\d{4}", raw):
            return raw
    return ""

def extract_author_note(md_text: str) -> str:
    m = re.search(r"盘丝吐槽.*", md_text)
    if not m:
        return ""
    text = m.group(0)
    text = re.split(r"\n本章由", text)[0]
    text = re.sub(r"\*{1,2}", "", text)
    return text.strip()

# ── HTML 模板 ──
TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{html_title}</title>
<link rel="stylesheet" href="../css/style.css">
</head>
<body>

<div id="reading-progress"></div>

<nav class="top-nav">
  <div class="top-nav-inner">
    <a href="{index_path}">← 目录</a>
    <span class="nav-title">{nav_title}</span>
    <div class="reading-controls">
      <button id="font-dec" title="减小字号">A−</button>
      <span class="font-size-label" id="font-label">18</span>
      <button id="font-inc" title="增大字号">A+</button>
    </div>
  </div>
</nav>

<div class="chapter-wrapper">
  <div class="chapter-title">
    <div class="ch-label">{label}</div>
    <h1>{title}</h1>
  </div>

  <div class="chapter-content">

{content}

  </div>

  <div class="chapter-end">
    <span class="end-ornament">✦ ✦ ✦</span>
    {end_text}
  </div>

  <nav class="chapter-nav">
    <div class="nav-left">{prev_link}</div>
    <div class="nav-center">
      <a href="{index_path}">☰ 目录</a>
    </div>
    <div class="nav-right">{next_link}</div>
  </nav>
</div>

<div id="tts-bar">
  <div class="tts-inner">
    <button id="tts-play">▶ 朗读本章</button>
    <button id="tts-pause" style="display:none;">⏸ 暂停</button>
    <button id="tts-stop" style="display:none;">⏹ 停止</button>
    <select id="tts-rate">
      <option value="0.8">慢速</option>
      <option value="1" selected>正常</option>
      <option value="1.2">快速</option>
    </select>
  </div>
</div>

<footer class="site-footer">{footer}</footer>

<script>
(function(){{
var h=document.documentElement;
window.addEventListener('scroll',function(){{
var p=(h.scrollTop-h.clientTop)/(h.scrollHeight-h.clientHeight)*100;
document.getElementById('reading-progress').style.width=Math.min(p,100)+'%';
}});
var sz=18,content=document.querySelector('.chapter-content'),label=document.getElementById('font-label');
document.getElementById('font-inc').addEventListener('click',function(){{if(sz<24){{sz+=1;content.style.fontSize=sz+'px';label.textContent=sz;}}}});
document.getElementById('font-dec').addEventListener('click',function(){{if(sz>14){{sz-=1;content.style.fontSize=sz+'px';label.textContent=sz;}}}});
var bar=document.getElementById('tts-bar'),playBtn=document.getElementById('tts-play'),pauseBtn=document.getElementById('tts-pause'),stopBtn=document.getElementById('tts-stop'),rateSelect=document.getElementById('tts-rate'),utt=null,paused=false;
function getText(){{var c=(document.querySelector('.chapter-content')||document.body).cloneNode(true);c.querySelectorAll('script,style,button,select,#tts-bar,.chapter-nav,.chapter-end,.site-footer').forEach(function(e){{e.remove()}});var t=(c.textContent||'').replace(/\\s+/g,' ').trim();return t.length>50000?t.slice(0,50000):t;}}
function speak(){{
if(utt)window.speechSynthesis.cancel();
utt=new SpeechSynthesisUtterance(getText());
utt.lang='zh-CN';utt.rate=parseFloat(rateSelect.value);
var v=window.speechSynthesis.getVoices(),zv=v.find(function(x){{return x.lang.startsWith('zh')}});
if(zv)utt.voice=zv;
utt.onstart=function(){{playBtn.style.display='none';pauseBtn.style.display='inline-block';stopBtn.style.display='inline-block';}};
utt.onend=function(){{playBtn.style.display='inline-block';playBtn.textContent='▶ 朗读本章';pauseBtn.style.display='none';stopBtn.style.display='none';utt=null;}};
utt.onerror=function(){{playBtn.style.display='inline-block';playBtn.textContent='▶ 朗读本章';pauseBtn.style.display='none';stopBtn.style.display='none';}};
window.speechSynthesis.speak(utt);
}}
playBtn.addEventListener('click',function(){{if(paused&&utt){{window.speechSynthesis.resume();paused=false;playBtn.style.display='none';pauseBtn.style.display='inline-block';return;}}speak();}});
pauseBtn.addEventListener('click',function(){{window.speechSynthesis.pause();paused=true;pauseBtn.style.display='none';playBtn.style.display='inline-block';playBtn.textContent='▶ 继续';}});
stopBtn.addEventListener('click',function(){{window.speechSynthesis.cancel();utt=null;paused=false;playBtn.style.display='inline-block';playBtn.textContent='▶ 朗读本章';pauseBtn.style.display='none';stopBtn.style.display='none';}});
bar.style.display='block';
}})();
</script>

</body>
</html>'''

# ── 章节标题收集 ──
def get_chapter_titles(novel: dict) -> dict:
    titles = {}
    target_dir = novel["target_dir"]
    source_dir = novel["source_dir"]
    if target_dir.exists():
        for f in sorted(target_dir.glob(f"{novel['prefix']}*{novel['ext']}")):
            m = re.search(rf"{re.escape(novel['prefix'])}(\d+){re.escape(novel['ext'])}", f.name)
            if not m: continue
            num = int(m.group(1))
            hm = re.search(r"<h1>(.+?)</h1>", f.read_text(encoding="utf-8"))
            if hm: titles[num] = hm.group(1)
    if source_dir.exists():
        for f in sorted(source_dir.glob("*.md")):
            try:
                num, title = novel["parse_file"](f.name)
                if num not in titles: titles[num] = title
            except: pass
    return titles

def build_nav(num: int, novel: dict, all_titles: dict) -> tuple:
    prefix, ext = novel["prefix"], novel["ext"]
    file_num = novel.get("file_num", str)
    nums = sorted(all_titles.keys())
    idx = nums.index(num) if num in nums else -1
    prev_html = ""
    next_html = ""
    if idx > 0:
        pn, pt = nums[idx - 1], all_titles.get(nums[idx - 1], "")
        prev_html = f'<a href="{prefix}{file_num(pn)}{ext}">← {pt}</a>'
    if idx < len(nums) - 1:
        nn, nt = nums[idx + 1], all_titles.get(nums[idx + 1], "")
        next_html = f'<a href="{prefix}{file_num(nn)}{ext}">{nt} →</a>'
    return prev_html, next_html

def generate_chapter(num: int, novel: dict, nav_prev: str, nav_next: str) -> str:
    source_dir = novel["source_dir"]
    fn_prefix = "第" + str(num).zfill(2) + "章"
    md_file = None

    for f in sorted(source_dir.glob("*.md")):
        if f.name.startswith(fn_prefix): md_file = f; break
    if num == 0:
        for f in source_dir.glob("序章*.md"): md_file = f; break
    if not md_file: return None

    md_text = md_file.read_text(encoding="utf-8")
    title = extract_zh_title(md_text) or novel["parse_file"](md_file.name)[1]

    label_str = novel["label_num"](num)
    label = novel["label_fmt"](label_str, title)
    content_html = md_to_html(md_text)
    html_title = novel["html_title_fmt"](label_str, title)
    end_text = novel["end_fmt"](label_str)

    extras = []
    u = extract_update_info(md_text)
    if u: extras.append(f'<p>\n<em>{u}</em>\n</p>')
    a = extract_author_note(md_text)
    if a: extras.append(f'<div class="author-note">\n<strong>{a}</strong>\n</div>')
    if extras:
        content_html += "\n<hr>\n" + "\n".join(extras)

    return TEMPLATE.format(
        html_title=html_title,
        index_path=novel["index_path"],
        nav_title=novel["nav_title"],
        label=label, title=title.strip(),
        content=content_html,
        end_text=end_text,
        prev_link=nav_prev, next_link=nav_next,
        footer=novel["footer"],
    )

# ── 交互式菜单 ──
def interactive_menu():
    print("=" * 50)
    print("  盘丝洞部署 v2.1")
    print("=" * 50)
    print()
    print("操作模式：")
    print("  [1] 本地同步（盘丝洞 MD → 本地网站）")
    print("  [2] GitHub 推送（本地 → GitHub）")
    print("  [3] 全流程（1 + 2）")
    mode = input("请输入 [1/2/3]: ").strip()
    while mode not in ("1", "2", "3"):
        mode = input("请重新输入 [1/2/3]: ").strip()
    mode = int(mode)

    print()
    print("同步范围：")
    print("  [1] 更新（对比差异，仅更新缺失/变更章节）")
    print("  [2] 全量（不对比，直接全部替换）")
    scope = input("请输入 [1/2]: ").strip()
    while scope not in ("1", "2"):
        scope = input("请重新输入 [1/2]: ").strip()
    scope = int(scope)

    print()
    return mode, scope


# ── 本地同步：更新（对比缺失章节） ──
def local_sync_update():
    """对比源MD与本地HTML，仅生成缺失章节。"""
    any_missing = False
    for novel in NOVELS:
        source_dir, target_dir = novel["source_dir"], novel["target_dir"]
        prefix, ext = novel["prefix"], novel["ext"]
        if not source_dir.exists() or not target_dir.exists():
            continue

        source_files = {}
        for f in source_dir.glob("*.md"):
            try:
                num, title = novel["parse_file"](f.name)
                source_files[num] = f
            except: continue

        existing = set()
        file_num = novel.get("file_num", str)
        for f in target_dir.glob(f"{prefix}*{ext}"):
            m = re.search(rf"{re.escape(prefix)}(\d+){re.escape(ext)}", f.name)
            if m: existing.add(int(m.group(1)))

        missing = sorted(set(source_files.keys()) - existing)
        if not missing:
            print(f"[{novel['id']}] ✅ 全部完整（{len(source_files)} 章）")
            continue

        any_missing = True
        print(f"\n[{novel['id']}] 缺 {len(missing)} 章: {missing}")
        all_titles = get_chapter_titles(novel)
        for m in missing:
            if m not in all_titles:
                all_titles[m] = novel["parse_file"](source_files[m].name)[1]

        for num in missing:
            nav_prev, nav_next = build_nav(num, novel, all_titles)
            html = generate_chapter(num, novel, nav_prev, nav_next)
            if html is None:
                print(f"  [!] 无法生成 {prefix}{file_num(num)}{ext}")
                continue
            fpath = target_dir / f"{prefix}{file_num(num)}{ext}"
            fpath.write_text(html, encoding="utf-8")
            print(f"  ✓ {fpath.name}")

    if not any_missing:
        print("\n✅ 所有章节已完整，无需更新")


# ── 本地同步：全量（全部重生成） ──
def local_sync_full():
    """清空本地章节HTML，全部重新生成。"""
    for novel in NOVELS:
        source_dir, target_dir = novel["source_dir"], novel["target_dir"]
        if not source_dir.exists() or not target_dir.exists():
            continue

        source_files = {}
        for f in sorted(source_dir.glob("*.md")):
            try:
                num, title = novel["parse_file"](f.name)
                source_files[num] = f
            except: continue
        if not source_files: continue

        prefix, ext = novel["prefix"], novel["ext"]
        file_num = novel.get("file_num", str)
        all_titles = {}

        for num, f in source_files.items():
            md_text = f.read_text(encoding="utf-8")
            title = extract_zh_title(md_text) or novel["parse_file"](f.name)[1]
            all_titles[num] = title

        # 清理旧文件
        for f in target_dir.glob(f"{prefix}*{ext}"):
            f.unlink()
            print(f"  ✗ 删除旧文件: {f.name}")

        print(f"\n[{novel['id']}] 全量生成 {len(source_files)} 章...")
        for num in sorted(source_files.keys()):
            nav_prev, nav_next = build_nav(num, novel, all_titles)
            html = generate_chapter(num, novel, nav_prev, nav_next)
            if html is None:
                print(f"  [!] 无法生成 {prefix}{file_num(num)}{ext}")
                continue
            fpath = target_dir / f"{prefix}{file_num(num)}{ext}"
            fpath.write_text(html, encoding="utf-8")
            print(f"  ✓ {fpath.name}")


# ── GitHub 推送 ──
def git_push(force=False):
    print("推送至 GitHub...\n")
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain"],
        capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("无变更，无需推送")
        return

    subprocess.run(["git", "-C", str(REPO), "add", "-A"])
    r = subprocess.run(
        ["git", "-C", str(REPO), "commit", "-m", "sync: 自动同步章节内容 from 盘丝洞"],
        capture_output=True, text=True
    )
    if r.returncode != 0 and "nothing to commit" not in r.stderr:
        print(f"[!] commit 失败: {r.stderr}")
        return

    cmd = ["git", "-C", str(REPO), "push"]
    if force:
        cmd.append("--force")
        print("  全量模式：force push...")

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"[!] push 失败: {r.stderr}")
    else:
        print("✓ 已推送至 GitHub")


# ── 主流程 ──
def main():
    is_interactive = "--interactive" in sys.argv or not any(
        a in sys.argv for a in ("--sync", "--push", "--full")
    )

    if is_interactive:
        mode, scope = interactive_menu()
        do_sync = mode in (1, 3)
        do_push = mode in (2, 3)
        do_full = scope == 2
    else:
        do_sync = "--sync" in sys.argv
        do_push = "--push" in sys.argv
        do_full = "--full" in sys.argv

    # ── 本地同步 ──
    if do_sync:
        print("=" * 50)
        print("  本地同步：盘丝洞 MD → 本地网站")
        print("=" * 50)
        print()

        if do_full:
            print("▶ 全量模式：清空旧文件，全部重新生成\n")
            local_sync_full()
        else:
            print("▶ 更新模式：对比源MD与本地HTML，仅补充缺失章节\n")
            local_sync_update()

    # ── GitHub 推送 ──
    if do_push:
        print()
        print("=" * 50)
        print("  GitHub 推送")
        if do_full:
            print("  （全量模式：force push 覆盖远端）")
        else:
            print("  （更新模式：仅推送本地变更）")
        print("=" * 50)
        print()

        git_push(force=do_full)

if __name__ == "__main__":
    main()
