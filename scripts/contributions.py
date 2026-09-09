"""Generate the current calendar year's README charts from the public GitHub calendar.

No token or third-party chart service is required. Missing/unrecognized source
data fails the update, preserving the last valid SVG. Run with Python 3.10+.
"""

import argparse
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.request import Request, urlopen


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = {}
        self.tips = {}
        self.tip_id = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('td', 'rect') and attrs.get('data-date') and attrs.get('id'):
            self.cells[attrs['id']] = attrs['data-date']
        if tag == 'tool-tip':
            self.tip_id = attrs.get('for')
            self.parts = []

    def handle_data(self, data):
        if self.tip_id:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.tip_id:
            self.tips[self.tip_id] = ''.join(self.parts).strip()
            self.tip_id = None


def parse_calendar(html, today):
    parser = CalendarParser()
    parser.feed(html)
    first = date(today.year, 1, 1)
    counts = {}
    for cell_id, raw_date in parser.cells.items():
        day = date.fromisoformat(raw_date)
        if not first <= day <= today:
            continue
        tooltip = parser.tips.get(cell_id, '')
        match = re.match(r'^(No|[\d,]+) contributions? on\b', tooltip)
        if not match:
            raise ValueError(f'Unrecognized contribution count for {day}')
        if day in counts:
            raise ValueError(f'Duplicate calendar date: {day}')
        counts[day] = 0 if match[1] == 'No' else int(match[1].replace(',', ''))
    expected = {first + timedelta(days=i) for i in range((today - first).days + 1)}
    if counts.keys() != expected:
        raise ValueError('Incomplete calendar; refusing to replace the existing chart')
    return dict(sorted(counts.items()))


def render(counts, today, username):
    year = today.year
    total = sum(counts.values())
    active = sum(n > 0 for n in counts.values())
    peak = max(counts.values(), default=0)
    months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    monthly = [sum(n for day, n in counts.items() if day.month == m) for m in range(1, 13)]
    colors = ['#161b22', '#0e3159', '#1458a0', '#2188e5', '#79c0ff']
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="630" viewBox="0 0 960 630" role="img" aria-labelledby="title desc">',
           f'<title id="title">Contribuições de {escape(username)} em {year}</title>',
           f'<desc id="desc">De 1 de janeiro a {today:%d/%m/%Y}: {total} contribuições, {active} dias ativos. Resumo, totais mensais e calendário diário. Datas futuras não representam zero contribuições.</desc>',
           '<rect width="960" height="630" rx="18" fill="#0d1117"/>',
           '<g font-family="DejaVu Sans,Arial,sans-serif">']

    def text(x, y, value, size=13, color='#c9d1d9', **attrs):
        extra = ' '.join(f'{k.replace("_", "-")}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
        out.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" {extra}>{escape(str(value))}</text>')

    text(32, 42, f'Meu GitHub em {year}', 25, '#58a6ff', font_weight=700)
    text(32, 66, f'01/01/{year} a {today:%d/%m/%Y} · contribuições visíveis no perfil', 12, '#8b949e')
    for i, (label, value) in enumerate([('Contribuições no ano', total), ('Dias com contribuições', active), ('Maior total em um dia', peak)]):
        x = 32 + i * 304
        out.append(f'<rect x="{x}" y="88" width="288" height="91" rx="10" fill="#161b22"/>')
        text(x + 18, 115, label, 13, '#8b949e')
        text(x + 18, 157, f'{value:,}'.replace(',', '.'), 32, '#f0f6fc', font_weight=700)

    text(32, 218, 'Contribuições por mês', 17, '#58a6ff', font_weight=600)
    text(928, 218, '* mês em andamento', 11, '#8b949e', text_anchor='end')
    maximum = max(1, max(monthly))
    for i, value in enumerate(monthly):
        x = 49 + i * 74
        future = i + 1 > today.month
        h = 108 * value / maximum
        label = months[i] + ('*' if i + 1 == today.month else '')
        out.append(f'<line x1="{x}" y1="364" x2="{x+48}" y2="364" stroke="#30363d"/>')
        if not future and value:
            out.append(f'<rect x="{x}" y="{364-h:.1f}" width="48" height="{h:.1f}" rx="4" fill="#2188e5"><title>{months[i]}: {value} contribuições</title></rect>')
        text(x + 24, 352 - h if value else 350, '—' if future else value, 12, '#8b949e' if future else '#c9d1d9', text_anchor='middle')
        text(x + 24, 388, label, 12, '#484f58' if future else '#8b949e', text_anchor='middle')

    text(32, 433, 'Calendário de contribuições', 17, '#58a6ff', font_weight=600)
    first = date(year, 1, 1)
    offset = (first.weekday() + 1) % 7
    for i, name in [(1, 'Seg'), (3, 'Qua'), (5, 'Sex')]:
        text(32, 480 + i * 15, name, 10, '#8b949e')
    for index in range((date(year + 1, 1, 1) - first).days):
        day = first + timedelta(days=index)
        week, weekday = divmod(index + offset, 7)
        x, y = 68 + week * 16, 470 + weekday * 15
        if day.day == 1:
            text(x, 460, months[day.month - 1], 10, '#8b949e')
        future = day > today
        value = counts.get(day, 0)
        level = 0 if not value else min(4, max(1, (value * 4 + peak - 1) // peak))
        fill = '#0d1117' if future else colors[level]
        label = f'{day:%d/%m/%Y}: ' + ('data futura' if future else f'{value} contribuições')
        out.append(f'<rect x="{x}" y="{y}" width="12" height="11" rx="2" fill="{fill}" stroke="#21262d" stroke-width="0.5"><title>{label}</title></rect>')

    text(32, 608, f'Atualizado em {today:%d/%m/%Y} · fonte: calendário público do GitHub', 11, '#8b949e')
    text(751, 608, 'Menos', 10, '#8b949e')
    for i, color in enumerate(colors):
        out.append(f'<rect x="{791+i*17}" y="598" width="12" height="11" rx="2" fill="{color}"/>')
    text(884, 608, 'Mais', 10, '#8b949e')
    out.append('</g></svg>')
    return '\n'.join(out) + '\n'


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--username', default='EvanAmorim18')
    cli.add_argument('--output', type=Path, default=Path('assets/contributions-year.svg'))
    args = cli.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9-]+', args.username):
        cli.error('Invalid GitHub username')
    today = datetime.now(timezone.utc).date()
    url = f'https://github.com/users/{args.username}/contributions?from={today.year}-01-01&to={today.year}-12-31'
    request = Request(url, headers={'User-Agent': 'GitHubProfileReadme/1.0', 'Accept-Language': 'en-US'})
    with urlopen(request, timeout=45) as response:
        html = response.read().decode('utf-8')
    counts = parse_calendar(html, today)
    svg = render(counts, today, args.username)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(svg, encoding='utf-8')
    temporary.replace(args.output)
    print(f'{today.year}: {sum(counts.values())} contributions across {len(counts)} calendar days')


if __name__ == '__main__':
    main()
