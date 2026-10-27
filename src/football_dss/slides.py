"""Build a draft deck (reports/presentation.pptx) and defense notes (reports/defense_notes.md)
from the pipeline outputs. Every number on the slides comes from outputs/*.csv.

    python -m football_dss.slides        (runs automatically at the end of the pipeline)
"""
import json

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from . import config

PITCH = RGBColor(0x0B, 0x3D, 0x2E)
PITCH_2 = RGBColor(0x14, 0x53, 0x2D)
GOLD = RGBColor(0xD4, 0xA0, 0x17)
INK = RGBColor(0x1B, 0x1F, 0x1E)
MUTED = RGBColor(0x5F, 0x6B, 0x66)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TINT = RGBColor(0xEE, 0xF4, 0xF1)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1E, 0x84, 0x49)
HEAD, BODY = "Cambria", "Calibri"
W, H = 13.333, 7.5


# ------------------------------------------------------------------ helpers
def load(name):
    p = config.OUTPUTS / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def m(eur):
    return f"{eur / 1e6:.1f} млн €" if pd.notna(eur) else "-"


def pct(x):
    return f"{x:.0%}" if pd.notna(x) else "-"


def new_slide(prs, dark=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = PITCH if dark else WHITE
    return s


def text(slide, x, y, w, h, paras, size=16, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, space=6):
    """paras: str or list of str / (str, {size,color,bold,font}) tuples."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    if isinstance(paras, str):
        paras = [paras]
    for i, p in enumerate(paras):
        t, opt = (p, {}) if isinstance(p, str) else p
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.space_after = Pt(space)
        r = para.add_run()
        r.text = t
        r.font.size = Pt(opt.get("size", size))
        r.font.bold = opt.get("bold", bold)
        r.font.name = opt.get("font", font)
        r.font.color.rgb = opt.get("color", color)
    return tb


def title(slide, t, dark=False, sub=None):
    # one line at most: long titles get a smaller size instead of wrapping into the subtitle
    size = 36 if len(t) <= 42 else 30 if len(t) <= 52 else 26
    text(slide, 0.6, 0.45, W - 1.2, 0.9, t, size=size, bold=True, font=HEAD, color=WHITE if dark else PITCH)
    if sub:
        text(slide, 0.6, 1.3, W - 1.2, 0.5, sub, size=16, color=GOLD if dark else MUTED)


def card(slide, x, y, w, h, fill=TINT):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.adjustments[0] = 0.08
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def badge(slide, x, y, label, d=0.5, fill=GOLD, color=PITCH):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.fill.background(); sh.shadow.inherit = False
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = str(label)
    r.font.size = Pt(16); r.font.bold = True; r.font.name = HEAD; r.font.color.rgb = color
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE


def stat(slide, x, y, w, value, label, dark=False):
    text(slide, x, y, w, 0.9, value, size=40, bold=True, font=HEAD, color=GOLD if dark else PITCH)
    text(slide, x, y + 0.95, w, 0.6, label, size=13, color=WHITE if dark else MUTED)


def table(slide, df, x, y, w, row_h=0.4, size=12, col_w=None):
    if df.empty:
        text(slide, x, y, w, 0.5, "нет данных", size=14, color=MUTED)
        return
    rows, cols = df.shape[0] + 1, df.shape[1]
    t = slide.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(row_h * rows)).table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Inches(cw)
    for j, c in enumerate(df.columns):
        _cell(t.cell(0, j), str(c), size, WHITE, PITCH, bold=True)
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(row):
            _cell(t.cell(i, j), _fmt(v), size, INK, TINT if i % 2 else WHITE)


def _fmt(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1000:
        return str(int(v))
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"
    return str(v)


def _cell(cell, s, size, color, fill, bold=False):
    cell.fill.solid(); cell.fill.fore_color.rgb = fill
    cell.margin_left = cell.margin_right = Inches(0.08)
    tf = cell.text_frame
    tf.paragraphs[0].text = ""
    r = tf.paragraphs[0].add_run(); r.text = s
    r.font.size = Pt(size); r.font.bold = bold; r.font.name = BODY; r.font.color.rgb = color


def bar_chart(slide, cats, values, x, y, w, h, ttl, horizontal=False, colors=None, fmt="0.0"):
    data = CategoryChartData()
    data.categories = [str(c) for c in cats]
    data.add_series(ttl, [float(v) for v in values])
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    ch = slide.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), data).chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = ttl
    tp = ch.chart_title.text_frame.paragraphs[0].runs[0].font
    tp.size = Pt(14); tp.bold = True; tp.name = BODY; tp.color.rgb = INK
    ch.font.size = Pt(12); ch.font.name = BODY; ch.font.color.rgb = MUTED
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = fmt; dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(12); dl.font.color.rgb = INK
    ch.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xDD, 0xE3, 0xE0)
    ch.value_axis.format.line.fill.background()
    ch.value_axis.tick_labels.font.size = Pt(11)
    if min(values) >= 0:
        ch.value_axis.minimum_scale = 0          # honest bars: no truncated axis
    ch.category_axis.tick_labels.font.size = Pt(12)
    ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW  # labels clear of negative bars
    ser = plot.series[0]
    ser.invert_if_negative = False
    for i, v in enumerate(values):
        pt = ser.points[i].format.fill
        pt.solid()
        pt.fore_color.rgb = colors[i] if colors else PITCH_2
    # each data point carries its own invertIfNegative flag (default on -> white negative bars)
    for dpt in ser._element.findall(qn("c:dPt")):
        if dpt.find(qn("c:invertIfNegative")) is None:
            flag = dpt.makeelement(qn("c:invertIfNegative"), {"val": "0"})
            dpt.find(qn("c:idx")).addnext(flag)
    return ch


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


def picture(slide, name, x, y, w=None, h=None):
    p = config.FIGURES / f"{name}.png"
    if p.exists():
        slide.shapes.add_picture(str(p), Inches(x), Inches(y),
                                 width=Inches(w) if w else None, height=Inches(h) if h else None)


# ------------------------------------------------------------------ deck
def build():
    meta = json.load(open(config.OUTPUTS / "meta.json")) if (config.OUTPUTS / "meta.json").exists() else {}
    club = meta.get("club", config.TARGET_CLUB)
    dq, mv, mg, mb = load("data_quality"), load("metrics_value"), load("metrics_growth"), load("metrics_bust")
    bt, audit, scen = load("backtest"), load("squad_audit"), load("budget_scenarios")
    buys, sells, gems, twins = load("plan_buys"), load("plan_sells"), load("hidden_gems"), load("cheaper_twins")
    retr = load("similarity_validation")
    q = dict(zip(dq.get("check", []), dq.get("value", [])))

    ours = bt[bt["strategy"].str.contains("ours")].iloc[0] if not bt.empty else None
    by_ovr = bt[bt["strategy"] == "sort by overall"].iloc[0] if not bt.empty else None
    beats = ours is not None and ours["next-season role fit"] >= by_ovr["next-season role fit"] * 0.97 \
        and ours["avg price, M EUR"] < by_ovr["avg price, M EUR"]
    net = buys.get("fee", pd.Series(dtype=float)).sum() - sells.get("revenue", pd.Series(dtype=float)).sum()

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)

    # 1 title
    s = new_slide(prs, dark=True)
    text(s, 0.8, 2.0, 11.5, 1.6, "Moneyball 2.0: трансферное окно без переплат", size=44, bold=True, font=HEAD, color=WHITE)
    text(s, 0.8, 3.7, 11.5, 0.6, f"Система поддержки решений для спортивного директора · {club}", size=20, color=GOLD)
    text(s, 0.8, 5.6, 11.5, 0.5, "Команда: [имена участников]  ·  HW5 AI Football Intelligence", size=14, color=WHITE)
    notes(s, "Представиться. Одна фраза: мы построили инструмент, который помогает спортивному директору "
             "решить, кого купить, продать и отдать в аренду при ограниченном бюджете.")

    # 2 problem
    s = new_slide(prs)
    title(s, "Какое решение мы поддерживаем")
    blocks = [("Вопрос", "Кого купить, продать и отдать в аренду, чтобы усилить старт под 4-3-3 с прессингом, "
                         "не выходя за бюджет?"),
              ("Кто решает", "Спортивный директор вместе с главным тренером и финансовым отделом."),
              ("Результат", "План окна: список покупок и продаж, чистые траты, прирост качества и риски.")]
    for i, (h, b) in enumerate(blocks):
        x = 0.6 + i * 4.1
        card(s, x, 2.0, 3.8, 3.6)
        badge(s, x + 0.3, 2.3, i + 1)
        text(s, x + 0.3, 3.0, 3.2, 0.5, h, size=20, bold=True, font=HEAD, color=PITCH)
        text(s, x + 0.3, 3.6, 3.2, 1.9, b, size=15)
    text(s, 0.6, 6.1, 12, 0.6, f"Бюджет (допущение): {m(config.TRANSFER_BUDGET_EUR)} на трансферы, "
                               f"+{config.WAGE_BUDGET_EUR_WEEK/1e3:.0f} тыс. € в неделю на зарплаты, не больше {config.MAX_SIGNINGS} покупок",
         size=14, color=MUTED)
    notes(s, "Плохая постановка: 'проанализировали игроков FIFA'. Наша: конкретное решение с ограничениями. "
             "Бюджет — допущение, его можно менять ползунком в дашборде.")

    # 3 data
    s = new_slide(prs)
    title(s, "Данные: FIFA 17–23, снимок на конец сезона",
          sub="Kaggle · FIFA 23 Complete Player Dataset (male_players.csv)")
    stats = [(f"{int(q.get('player-seasons', 0)):,}".replace(",", " "), "игроко-сезонов"),
             (f"{int(q.get('unique players', 0)):,}".replace(",", " "), "уникальных игроков"),
             (f"{config.LAST_VERSION - config.FIRST_VERSION + 1}", "сезонов FIFA"),
             (str(q.get("missing value_eur", "-")), "без рыночной стоимости")]
    for i, (v, l) in enumerate(stats):
        stat(s, 0.6 + i * 3.1, 2.1, 2.9, v, l)
    text(s, 0.6, 4.0, 6.0, 3.0, [
        ("Подготовка", {"bold": True, "color": PITCH, "size": 18}),
        "Берём последний апдейт каждого сезона: это снимок на конец сезона",
        "Стоимость 0 € считаем пропуском, а не ценой",
        "release_clause и зарплату исключили как утечку",
        "Таргеты развития берём только из сезона t+1",
    ], size=15)
    table(s, dq.head(8), 7.0, 4.0, 5.7, row_h=0.32, size=11, col_w=[3.7, 2.0])
    notes(s, "Источник, объём, как чистили. Если спросят про дубликаты: внутри одного сезона у игрока "
             "несколько апдейтов, мы оставляем последний.")

    # 4 method
    s = new_slide(prs)
    title(s, "Как работает система")
    steps = [("Аудит", "role_fit под нашу тактику против 10 сильнейших клубов"),
             ("Модели", "fair value, рост в следующем сезоне, риск спада"),
             ("Скаутинг", "Moneyball-скор, кластеры стиля, дешёвые двойники"),
             ("Оптимизация", "MILP: максимум прироста XI при бюджете и глубине"),
             ("Решение", "план окна, сценарии бюджета, меморандум LLM")]
    for i, (h, b) in enumerate(steps):
        x = 0.6 + i * 2.5
        sh = s.shapes.add_shape(MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON,
                                Inches(x), Inches(2.1), Inches(2.4), Inches(0.9))
        sh.fill.solid(); sh.fill.fore_color.rgb = PITCH if i < 4 else GOLD
        sh.line.fill.background(); sh.shadow.inherit = False
        tf = sh.text_frame; tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        tf.margin_left = tf.margin_right = 0
        r = tf.paragraphs[0].add_run(); r.text = h
        r.font.size = Pt(14); r.font.bold = True; r.font.name = BODY
        r.font.color.rgb = WHITE if i < 4 else PITCH
        text(s, x + 0.1, 3.3, 2.2, 1.6, b, size=14)
    card(s, 0.6, 5.0, 12.1, 1.7)
    text(s, 0.9, 5.2, 11.5, 1.4, [
        ("Главная идея", {"bold": True, "color": PITCH, "size": 16}),
        "Рынок (и рейтинг FIFA) оценивает игрока «в целом». Нам нужен игрок под наш стиль. "
        "Разница role_fit − overall показывает, где рынок недооценивает подходящих нам игроков.",
    ], size=15)
    notes(s, "Пройти по шагам слева направо. Почему MILP, а не жадный выбор: он учитывает бюджет, "
             "зарплаты, лимит покупок и глубину состава одновременно.")

    # 5 squad audit
    s = new_slide(prs)
    a = audit[audit["slots"] > 0] if not audit.empty else audit
    worst = a.sort_values("gap_vs_elite").head(3) if not a.empty else a
    title(s, f"Аудит: где {club} слабее элиты",
          sub="Средний role_fit стартовых игроков минус тот же показатель у 10 сильнейших клубов")
    if not a.empty:
        a2 = a.sort_values("gap_vs_elite")
        bar_chart(s, a2["group"], a2["gap_vs_elite"], 0.6, 1.9, 7.4, 5.0, "Отставание от элиты по позициям",
                  horizontal=True, colors=[RED if v < 0 else GREEN for v in a2["gap_vs_elite"]])
    y = 2.0
    for _, r in worst.iterrows():
        card(s, 8.4, y, 4.3, 1.5)
        text(s, 8.65, y + 0.15, 3.9, 0.5, f"{r['group']}: {r['gap_vs_elite']:+.1f}", size=22, bold=True, font=HEAD, color=RED)
        text(s, 8.65, y + 0.75, 3.9, 0.7, f"в составе {r['players']} (минимум {r['min_depth']}), средний возраст {r['avg_age']}",
             size=13, color=MUTED)
        y += 1.7
    notes(s, "Обозначения: GK вратарь, CB центральный защитник, FB крайний, DM опорник, CM центральный, "
             "AM атакующий полузащитник, W вингер, ST нападающий. Приоритет считается по отставанию, "
             "нехватке глубины и возрасту.")

    # 6 model quality
    s = new_slide(prs)
    title(s, "Можно ли доверять моделям", sub=f"Обучение на FIFA ≤ {config.LAST_VERSION - 1}, тест на FIFA {config.LAST_VERSION}: проверка во времени, без утечки")
    text(s, 0.6, 1.95, 6, 0.4, "Справедливая стоимость", size=16, bold=True, color=PITCH)
    table(s, mv.round(3), 0.6, 2.4, 6.0, row_h=0.38, size=12, col_w=[2.7, 1.1, 0.9, 1.3])
    text(s, 6.9, 1.95, 6, 0.4, "Рост в следующем сезоне", size=16, bold=True, color=PITCH)
    table(s, mg.round(3), 6.9, 2.4, 5.8, row_h=0.38, size=12, col_w=[3.4, 1.2, 1.2])
    text(s, 6.9, 4.0, 6, 0.4, "Риск спада (−2 и больше)", size=16, bold=True, color=PITCH)
    table(s, mb.round(3), 6.9, 4.45, 5.8, row_h=0.38, size=12, col_w=[2.8, 1.0, 0.9, 1.1])
    if not retr.empty:
        hit = retr.iloc[:, 1].mean(); rnd = retr["random"].mean()
        stat(s, 0.6, 4.5, 6.0, f"{hit:.0%}", f"top-5 hit rate поиска похожих игроков (случайно: {rnd:.1%})")
    notes(s, "Каждую модель сравниваем с простым baseline. Если модель не лучше baseline, честно говорим об этом. "
             "Fair value для текущего сезона считается out-of-fold, иначе цена игрока утекает в прогноз.")

    # 7 backtest
    s = new_slide(prs)
    title(s, "Бэктест: лучше ли наш скор простого рейтинга",
          sub=f"Списки на FIFA {config.LAST_VERSION - 1}, результат смотрим в FIFA {config.LAST_VERSION}")
    if not bt.empty:
        lab = ["По overall", "Overall / цена", "Moneyball"]
        cols = [MUTED, MUTED, GOLD]
        bar_chart(s, lab, bt["next-season role fit"], 0.6, 1.9, 4.0, 4.4, "Role fit через год", colors=cols)
        bar_chart(s, lab, bt["avg price, M EUR"], 4.7, 1.9, 4.0, 4.4, "Средняя цена, млн €", colors=cols)
        bar_chart(s, lab, bt["bust rate"] * 100, 8.8, 1.9, 4.0, 4.4, "Доля спадов, %", colors=cols, fmt="0")
        verdict = ("Moneyball даёт почти тот же уровень за меньшие деньги" if beats else
                   "Moneyball не обогнал простой рейтинг: это тоже результат, разбираем почему")
        text(s, 0.6, 6.5, 12, 0.6, verdict, size=18, bold=True, color=PITCH)
    notes(s, "Ключевой слайд: показывает, чем система лучше простого рейтинга. Списки строятся только по "
             "информации на момент сезона t. Если результат отрицательный, так и говорим: преподаватель "
             "прямо пишет, что отрицательный результат при грамотном исследовании — тоже результат.")

    # 8 recommendation
    s = new_slide(prs)
    title(s, "Рекомендация: кого покупаем", sub=f"Чистые траты {m(net)} из {m(config.TRANSFER_BUDGET_EUR)}")
    n = max(len(buys), 1)
    cw = min(3.0, (12.1 - 0.3 * (n - 1)) / n)
    for i, (_, b) in enumerate(buys.head(4).iterrows()):
        x = 0.6 + i * (cw + 0.3)
        card(s, x, 2.0, cw, 3.4)
        badge(s, x + 0.25, 2.25, b["pos_group"], d=0.7)
        text(s, x + 0.25, 3.1, cw - 0.5, 0.5, str(b["short_name"]), size=20, bold=True, font=HEAD, color=PITCH)
        text(s, x + 0.25, 3.6, cw - 0.5, 1.8, [
            f"{b['age']:.0f} лет · {b['club_name']}",
            f"overall {b['overall']:.0f} → прогноз {b.get('overall_next_pred', float('nan')):.0f}",
            f"role fit {b['role_fit']:.1f}",
            f"цена ~{m(b['fee'])}",
            f"риск спада {pct(b['bust_risk'])}",
        ], size=13, space=3)
    if buys.empty:
        text(s, 0.6, 2.2, 12, 0.6, "Оптимизатор не нашёл покупок в рамках бюджета", size=18, color=MUTED)
    sell_txt = ", ".join(f"{r['short_name']} ({m(r['revenue'])})" for _, r in sells.iterrows()) or "нет"
    text(s, 0.6, 5.8, 12, 0.9, f"Продаём: {sell_txt}", size=16, color=PITCH)
    notes(s, "Для каждого игрока объяснить: почему он, а не альтернатива из шорт-листа (outputs/shortlists.csv). "
             "Цена = стоимость FIFA × 1.2, это допущение.")

    # 9 budget
    s = new_slide(prs)
    title(s, "Что будет, если урезать бюджет", sub="Тот же оптимизатор при 100 / 80 / 60 / 40% бюджета")
    if not scen.empty:
        bar_chart(s, scen["budget share"], scen["XI role-fit gain"], 0.6, 1.9, 5.6, 4.8, "Прирост качества старта")
        t = scen[["budget share", "buys", "net spend, M EUR"]].rename(
            columns={"budget share": "Бюджет", "buys": "Покупки", "net spend, M EUR": "Траты, млн €"})
        table(s, t, 6.5, 2.0, 6.2, row_h=0.6, size=11, col_w=[1.0, 3.9, 1.3])
    notes(s, "Готовый ответ на вопрос 'что если бюджет уменьшить на 20%': строка 80%. "
             "В дашборде то же самое можно показать вживую ползунком.")

    # 10 hidden gems
    s = new_slide(prs)
    title(s, "Неочевидные кандидаты", sub="Overall у них средний, но под наш стиль они подходят лучше, чем показывает рейтинг")
    cols = ["short_name", "age", "club_name", "pos_group", "overall", "role_fit", "value_eur"]
    g = gems.reindex(columns=cols).head(6).copy()
    if not g.empty:
        g["value_eur"] = g["value_eur"].map(m)
        g.columns = ["Игрок", "Возраст", "Клуб", "Поз.", "Overall", "Role fit", "Стоимость"]
    table(s, g, 0.6, 2.0, 7.4, row_h=0.45, size=12, col_w=[1.6, 0.8, 1.6, 0.6, 0.9, 0.9, 1.0])
    if not twins.empty:
        text(s, 8.4, 2.0, 4.3, 0.5, "Дешёвые двойники звезды", size=18, bold=True, font=HEAD, color=PITCH)
        tw = [f"{r['short_name']} · {m(r['value_eur'])} · сходство {r['style_similarity']:.2f}"
              for _, r in twins.head(5).iterrows()]
        text(s, 8.4, 2.6, 4.3, 3.5, tw, size=14)
    notes(s, "Это и есть дополнительный вызов из задания: недооценённый игрок, который не выглядит очевидным "
             "по стандартной статистике. Двойники ищутся по форме профиля атрибутов, а не по уровню.")

    # 11 pitfalls
    s = new_slide(prs)
    title(s, "Ловушки и как мы их обошли")
    traps = [("Утечка данных", "Убрали release_clause и зарплату; таргеты только из t+1; fair value out-of-fold"),
             ("Разные позиции", "Скоры, z-нормировки, кластеры и бенчмарки считаются внутри группы позиций"),
             ("FIFA ≠ реальный рынок", "value_eur — формула EA; комиссия ×1.2 и скидка ×0.85 — наши допущения"),
             ("Разные лиги и время", "75 в АПЛ ≠ 75 во второй лиге; снимок 2022/23 уже устарел")]
    for i, (h, b) in enumerate(traps):
        x, y = 0.6 + (i % 2) * 6.15, 1.8 + (i // 2) * 2.6
        card(s, x, y, 5.95, 2.3)
        badge(s, x + 0.3, y + 0.3, "!")
        text(s, x + 1.0, y + 0.3, 4.7, 0.5, h, size=20, bold=True, font=HEAD, color=PITCH)
        text(s, x + 1.0, y + 0.95, 4.7, 1.3, b, size=15)
    notes(s, "Задание требует минимум две ловушки; у нас четыре, и для каждой показано, как она повлияла "
             "на методологию. Корреляция ≠ причинность: важность признаков показывает связь, а не причину.")

    # 12 conclusion
    s = new_slide(prs, dark=True)
    title(s, "Вывод", dark=True)
    names = ", ".join(buys["short_name"].astype(str)) if not buys.empty else "—"
    text(s, 0.6, 1.8, 12, 4.5, [
        (f"Покупаем: {names}", {"size": 22, "bold": True, "color": GOLD}),
        f"Чистые траты {m(net)}, укладываемся в бюджет {m(config.TRANSFER_BUDGET_EUR)}",
        "Система выбирает под наш стиль и бюджет, а не просто по рейтингу" if beats else
        "Бэктест показал, где простой рейтинг пока не уступает нашему скору: это следующий шаг доработки",
        ("Риски: рейтинги FIFA — приближение; кандидатов нужно досмотреть вживую", {"color": WHITE}),
        ("Дальше: реальные данные о матчах (StatsBomb), реальные трансферные цены", {"color": WHITE}),
    ], size=18, color=WHITE, space=12)
    gain = buys["gain"].sum() if "gain" in buys else 0
    for i, (v, l) in enumerate([(m(net), "чистые траты"), (str(len(buys)), "покупок"),
                                (f"+{gain:.1f}", "прирост role fit стартового состава")]):
        stat(s, 0.6 + i * 4.1, 5.2, 3.8, v, l, dark=True)
    notes(s, "Закончить конкретным решением и рисками. Затем перейти к демо дашборда (streamlit run app.py).")

    # 13 AI & roles
    s = new_slide(prs)
    title(s, "Использование AI и роли в команде")
    card(s, 0.6, 1.8, 5.95, 3.4)
    text(s, 0.9, 2.0, 5.4, 4.5, [
        ("LLM в проекте", {"bold": True, "color": PITCH, "size": 18}),
        "Меморандум для директора: LLM получает только посчитанные числа",
        "[для чего ещё использовали AI]",
        "[как проверяли результаты]",
    ], size=15)
    card(s, 6.75, 1.8, 5.95, 3.4)
    text(s, 7.05, 2.0, 5.4, 4.5, [
        ("Роли", {"bold": True, "color": PITCH, "size": 18}),
        "[имя] — данные и качество данных",
        "[имя] — модели и валидация",
        "[имя] — аудит, скаутинг, оптимизатор",
        "[имя] — дашборд и презентация",
    ], size=15)
    notes(s, "ЗАПОЛНИТЬ КОМАНДОЙ. Преподаватель спросит, какой результат каждый лично получил или проверил.")

    out = config.REPORTS / "presentation.pptx"
    prs.save(out)
    defense_notes(club, mv, mg, mb, bt, scen, buys, net, beats)
    print(f"[slides] {out}")
    return out


def defense_notes(club, mv, mg, mb, bt, scen, buys, net, beats):
    def best(dfm, metric, low=True):
        if dfm.empty:
            return "-"
        r = dfm.sort_values(metric, ascending=low).iloc[0]
        return f"{r['model']} ({metric} = {r[metric]:.3f})"

    s80 = scen[scen["budget share"] == "80%"].iloc[0] if not scen.empty and (scen["budget share"] == "80%").any() else None
    txt = f"""# Шпаргалка к защите: {club}

Числа взяты из outputs/*.csv последнего прогона. Перед защитой перечитайте reports/results.md.

**Почему такие методы?**
Gradient boosting хорошо работает с табличными данными, нелинейностями (возраст) и пропусками (у вратарей нет pace).
Линейная регрессия и простые таблицы оставлены как baseline. MILP вместо жадного выбора, потому что нужно
одновременно учесть трансферный и зарплатный бюджет, лимит покупок и минимальную глубину состава.
KMeans внутри каждой группы позиций: число кластеров выбирается по silhouette.

**Как проверяли качество?**
Time split: обучение на FIFA ≤ 22, тест на FIFA 23. Каждую модель сравнивали с baseline.
- Fair value, лучшая модель: {best(mv, 'MAE log-value')}
- Рост в следующем сезоне: {best(mg, 'MAE')}
- Риск спада: {best(mb, 'ROC-AUC', low=False)}
- Бэктест: списки на FIFA 22 сравнили с тем, что произошло в FIFA 23.

**Чем система лучше простого рейтинга?**
{"Moneyball-списки дают почти тот же уровень через год за меньшие деньги (слайд бэктеста)." if beats else
 "Честный ответ: в бэктесте наш скор не обогнал сортировку по overall. Объяснение: в FIFA рейтинг и цена сильно связаны, а веса скора мы задали вручную. Следующий шаг: подобрать веса на прошлых сезонах."}

**Что изменится, если урезать бюджет на 20%?**
{f"Покупки: {s80['buys']}; траты {s80['net spend, M EUR']:.1f} млн €; прирост XI {s80['XI role-fit gain']:.1f}." if s80 is not None else "см. budget_scenarios.csv"}

**Что такое role_fit?**
Взвешенное среднее атрибутов, которые важны для нашего стиля (4-3-3, прессинг) на данной позиции.
Веса заданы в config.py: это экспертное допущение, и его можно менять.

**Как избежали утечки данных?**
Убрали release_clause (EA считает его из value) и зарплату. Для моделей развития признаки берутся из сезона t,
таргет из t+1. Fair value текущего сезона считается out-of-fold (5 фолдов).

**Какое ограничение сильнее всего влияет на надёжность?**
Данные игровые: value_eur в FIFA — формула EA, а не реальная цена. Поэтому выводы о «недооценённости» — гипотезы
для скаутов, а не готовые решения.

**Что бы вы сделали при наличии дополнительных данных?**
Событийные данные матчей (StatsBomb: xG, прессинг, прогрессивные передачи), реальные трансферные цены и зарплаты
(Transfermarkt), травмы, минуты на поле.

**Почему именно эти покупки?** (план: {", ".join(buys['short_name'].astype(str)) if not buys.empty else "-"}, чистые траты {m(net)})
Для каждого игрока откройте outputs/shortlists.csv и сравните его с 2–3 альтернативами по role_fit, цене и риску.

**Что вы лично сделали и проверили?**
Каждый участник готовит ответ про свою часть (см. роли в README).
"""
    (config.REPORTS / "defense_notes.md").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    build()
