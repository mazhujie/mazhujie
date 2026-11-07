#!/usr/bin/env python3
"""Render a notebook-style calendar from the public GitHub contribution page.

Only published daily counts and levels are read. Parsing or network failures stop
the update, leaving the last successful images in place. No external packages.
"""
import argparse
import calendar
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

COLORS = ['#f0efdd', '#d9e3b9', '#b4c98c', '#8fa966', '#66844d']
INK = '#554b3d'
FONT = json.loads(Path(__file__).with_name('handwritten-glyphs.json').read_text())


class CalendarHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = []
        self.tips = {}
        self.current_tip = None
        self.words = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'td' and 'data-date' in attrs:
            self.cells.append(attrs)
        if tag == 'tool-tip':
            self.current_tip = attrs.get('for')
            if self.current_tip:
                self.tips[self.current_tip] = []

    def handle_endtag(self, tag):
        if tag == 'tool-tip':
            self.current_tip = None

    def handle_data(self, data):
        self.words.append(data)
        if self.current_tip:
            self.tips[self.current_tip].append(data)


def parse_calendar(source, login):
    parser = CalendarHTML()
    parser.feed(source)
    parser.close()
    days = []
    for cell in parser.cells:
        day = date.fromisoformat(cell['data-date'])
        tip = ' '.join(''.join(parser.tips.get(cell.get('id'), [])).split())
        count_match = re.match(r'^([\d,]+) contributions? on ', tip)
        if tip.startswith('No contributions on '):
            count = 0
        elif count_match:
            count = int(count_match[1].replace(',', ''))
        else:
            raise ValueError(f'Missing or unexpected contribution tooltip for {day}')
        level = int(cell['data-level'])
        if level not in range(5) or (count == 0) != (level == 0):
            raise ValueError(f'Invalid contribution level for {day}')
        days.append({'date': day.isoformat(), 'count': count, 'level': level})
    days.sort(key=lambda d: d['date'])
    if not 350 <= len(days) <= 378:
        raise ValueError('Expected a complete annual contribution calendar')
    for i, day in enumerate(days):
        if i and date.fromisoformat(day['date']) != date.fromisoformat(days[i-1]['date']) + timedelta(days=1):
            raise ValueError('Calendar contains duplicate or missing days')
    header = re.search(r'([\d,]+)\s+contributions?\s+in the last year', ' '.join(parser.words))
    if not header:
        raise ValueError('Could not validate the calendar total')
    total = int(header[1].replace(',', ''))
    if sum(d['count'] for d in days) != total:
        raise ValueError('Calendar total does not match the daily counts')
    return {'login': login, 'source': f'https://github.com/users/{login}/contributions',
            'as_of': days[-1]['date'], 'total': total, 'days': days}


def fetch_calendar(login):
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', login):
        raise ValueError('Invalid GitHub username')
    request = urllib.request.Request(
        f'https://github.com/users/{login}/contributions',
        headers={'User-Agent': 'hand-drawn-profile-calendar/1.0',
                 'Accept': 'text/html', 'Accept-Language': 'en-US,en;q=0.9'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                source = response.read(2_000_001)
            if len(source) > 2_000_000:
                raise ValueError('Unexpected calendar response size')
            return parse_calendar(source.decode('utf-8'), login)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def jitter(seed, amount=0.5):
    value = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xffffffff
    return (value - 0.5) * 2 * amount


def text(content, x, y, size, color=INK, anchor='start'):
    glyphs = FONT['glyphs']
    width = sum(glyphs[c]['width'] for c in content) * size / FONT['units_per_em']
    if anchor == 'end':
        x -= width
    elif anchor == 'middle':
        x -= width / 2
    pieces = [f'<g fill="{color}" aria-label="{html.escape(content, quote=True)}" '
              f'transform="translate({x:.2f} {y:.2f}) scale({size/FONT["units_per_em"]:.6f} {-size/FONT["units_per_em"]:.6f})">']
    cursor = 0
    for char in content:
        glyph = glyphs[char]
        if glyph['path']:
            pieces.append(f'<path transform="translate({cursor} 0)" d="{glyph["path"]}"/>')
        cursor += glyph['width']
    return ''.join(pieces) + '</g>'


def cell(day, x, y, size):
    a = jitter(day['date']+'a', .45)
    b = jitter(day['date']+'b', .4)
    r = 2.7
    shape = (f'M{x+r:.2f} {y+a:.2f} Q{x+size/2:.2f} {y+b:.2f} {x+size-r:.2f} {y:.2f} '
             f'Q{x+size:.2f} {y:.2f} {x+size+a:.2f} {y+r:.2f} L{x+size+b:.2f} {y+size-r:.2f} '
             f'Q{x+size:.2f} {y+size:.2f} {x+size-r:.2f} {y+size+a:.2f} '
             f'L{x+r:.2f} {y+size+b:.2f} Q{x:.2f} {y+size:.2f} {x+a:.2f} {y+size-r:.2f} '
             f'L{x+b:.2f} {y+r:.2f} Q{x:.2f} {y:.2f} {x+r:.2f} {y+a:.2f}Z')
    return (f'<g><title>{day["date"]}: {day["count"]} contributions</title>'
            f'<path d="{shape}" fill="{COLORS[day["level"]]}" '
            f'stroke="{"#c6ccb2" if day["level"] == 0 else "#879a67"}" stroke-width=".75"/>'
            f'<path d="M{x+3} {y+4} Q{x+size/2} {y+2.5} {x+size-3} {y+4}" '
            'fill="none" stroke="#fffdf2" stroke-width="1" opacity=".22"/></g>')


def weeks_from_days(days):
    first = date.fromisoformat(days[0]['date'])
    sunday = first - timedelta(days=(first.weekday()+1) % 7)
    weeks = []
    for day in days:
        d = date.fromisoformat(day['date'])
        column = (d-sunday).days // 7
        while len(weeks) <= column:
            weeks.append([])
        weeks[column].append(day)
    return weeks


def grid(weeks, x, y, pitch, size, label_size):
    pieces = []
    previous_month = None
    for column, week in enumerate(weeks):
        first = date.fromisoformat(week[0]['date'])
        last = date.fromisoformat(week[-1]['date'])
        month = (last.year, last.month)
        if month != previous_month:
            pieces.append(text(calendar.month_abbr[last.month], x+column*pitch, y-18, label_size, '#7f8165'))
            previous_month = month
        for day in week:
            d = date.fromisoformat(day['date'])
            row = (d.weekday()+1) % 7
            pieces.append(cell(day, x+column*pitch, y+row*pitch, size))
    for row, label in [(1, 'Mon'), (3, 'Wed'), (5, 'Fri')]:
        pieces.append(text(label, x-18, y+row*pitch+size*.85, label_size, '#85836d', anchor='end'))
    return ''.join(pieces)


def render(data, mobile=False):
    w, h = (1000, 1025) if mobile else (1400, 440)
    days = data['days']
    active = sum(d['count'] > 0 for d in days)
    weeks = weeks_from_days(days)
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
              f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc">',
              '<title id="title">Little by little - GitHub contributions</title>',
              f'<desc id="desc">{data["total"]} contributions on {active} active days. '
              f'{days[0]["date"]} through {data["as_of"]}. Source: GitHub public contribution calendar.</desc>',
              f'<rect width="{w}" height="{h}" fill="#fff"/>',
              '<defs><pattern id="grain" width="29" height="23" patternUnits="userSpaceOnUse">'
              '<circle cx="5" cy="8" r=".65" fill="#c7b795" opacity=".14"/>'
              '<circle cx="19" cy="19" r=".45" fill="#a9ac87" opacity=".18"/></pattern></defs>',
              f'<path d="M43 18 Q{w/2} 12 {w-44} 18 Q{w-17} 18 {w-17} 46 '
              f'L{w-16} {h-45} Q{w-16} {h-17} {w-44} {h-18} '
              f'Q{w/2} {h-12} 44 {h-18} Q17 {h-18} 17 {h-45} L18 45 Q18 18 43 18Z" '
              'fill="#fff9ec" stroke="#adb58a" stroke-width="2.1"/>',
              f'<rect x="25" y="25" width="{w-50}" height="{h-50}" rx="24" fill="url(#grain)"/>']
    for y in range(52, h-30, 34):
        pieces.append(f'<path d="M37 {y} Q{w/2} {y+1} {w-36} {y}" fill="none" stroke="#e4dfcb" stroke-width=".75" opacity=".42"/>')
    # Small paper-and-leaf accents, matching the existing notebook artwork.
    tape_x = w-200
    pieces.append(f'<path d="M{tape_x} 27 l146 14 -6 10 4 9 -8 7 3 10 -146 -13 7 -10 -4 -9 7 -8Z" fill="#c9d59b" opacity=".65"/>')
    if mobile:
        pieces.append(text('Little by little', 68, 110, 70))
        pieces.append('<path d="M68 128 Q260 114 535 126 M89 135 Q276 126 482 132" stroke="#a4b777" stroke-width="4" fill="none" stroke-linecap="round"/>')
        pieces.append(text(f'{data["total"]} contributions in the past year', 68, 189, 41))
        pieces.append(text(f'{active} active days', 68, 237, 34, '#7f8968'))
        cut = (len(weeks)+1)//2
        for group, yy in [(weeks[:cut], 345), (weeks[cut:], 678)]:
            first = date.fromisoformat(group[0][0]['date'])
            last = date.fromisoformat(group[-1][-1]['date'])
            label = f'{calendar.month_abbr[first.month]} {first.year} - {calendar.month_abbr[last.month]} {last.year}'
            pieces.append(text(label, 123, yy-65, 30, '#73795c'))
            pitch = min(30, 826/max(len(group), 1))
            pieces.append(grid(group, 123, yy, pitch, pitch-6, 27))
        legend_y, legend_x, legend_size, legend_pitch = 933, 650, 22, 31
        pieces.append(text('Less', legend_x-18, legend_y+20, 29, '#818269', anchor='end'))
        pieces.append(text('More', legend_x+5*legend_pitch+5, legend_y+20, 29, '#818269'))
        pieces.append(text(f'Updated {data["as_of"]} UTC', 68, 962, 27, '#8b8a73'))
    else:
        pieces.append(text('Little by little', 67, 92, 57))
        pieces.append('<path d="M68 109 Q270 99 483 108 M84 115 Q270 107 437 113" stroke="#a4b777" stroke-width="3.4" fill="none" stroke-linecap="round"/>')
        pieces.append(text(f'{data["total"]} contributions in the past year', 67, 154, 31))
        pieces.append(text(f'{active} active days', 1283, 151, 27, '#7f8968', anchor='end'))
        pieces.append(grid(weeks, 132, 214, 21.8, 17.4, 21))
        legend_y, legend_x, legend_size, legend_pitch = 381, 1134, 16, 23
        pieces.append(text('Less', legend_x-12, legend_y+14, 21, '#818269', anchor='end'))
        pieces.append(text('More', legend_x+5*legend_pitch+4, legend_y+14, 21, '#818269'))
        pieces.append(text(f'Updated {data["as_of"]} UTC', 68, 399, 23, '#8b8a73'))
    for level in range(5):
        pieces.append(f'<rect x="{legend_x+level*legend_pitch}" y="{legend_y}" width="{legend_size}" height="{legend_size}" rx="3" fill="{COLORS[level]}" stroke="#abb490" stroke-width=".7"/>')
    pieces.append('</svg>')
    return ''.join(pieces)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login', required=True)
    parser.add_argument('--input-html', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('assets'))
    args = parser.parse_args()
    data = parse_calendar(args.input_html.read_text(), args.login) if args.input_html else fetch_calendar(args.login)
    outputs = {'contributions.svg': render(data), 'contributions-mobile.svg': render(data, mobile=True),
               'contributions.json': json.dumps(data, indent=2)+'\n'}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (args.output_dir/name).write_text(content)
    print(f'Rendered {data["total"]} GitHub contributions across {len(data["days"])} days; as of {data["as_of"]}.')


if __name__ == '__main__':
    main()
