"""Tagebuch: zählen, fällige Einträge, Wochenrückblick, Anzeige."""
from datetime import datetime

from claude_pet import diary, personas


def _d(tmp_path):
    return diary.Diary(str(tmp_path / "tagebuch.json"))


def test_entry_due_in_the_evening_and_for_forgotten_days(tmp_path):
    d = _d(tmp_path)
    d.set_minutes("2026-11-24", 200)
    d.count("commits", 3, day="2026-11-24")
    d.set_minutes("2026-11-25", 90)
    d.set_minutes("2026-11-23", 5)                           # zu wenig los: kein Eintrag
    assert d.due_entry(datetime(2026, 11, 25, 9, 0)) == "2026-11-24"
    d.set_entry("2026-11-24", "Heute drei Commits!")
    assert d.due_entry(datetime(2026, 11, 25, 9, 0)) is None  # heute erst am Abend
    assert d.due_entry(datetime(2026, 11, 25, 18, 5)) == "2026-11-25"
    d.failed.add("2026-11-25")
    assert d.due_entry(datetime(2026, 11, 25, 18, 5)) is None
    # gespeichert und wieder geladen
    d.save()
    again = _d(tmp_path)
    assert again.data["entries"]["2026-11-24"] == "Heute drei Commits!"
    assert again.data["days"]["2026-11-24"]["commits"] == 3


def test_facts_and_summary_only_list_what_happened(tmp_path):
    d = _d(tmp_path)
    d.set_minutes("2026-11-25", 150)
    d.count("eaten", 2, day="2026-11-25")
    d.add_word("TODO", day="2026-11-25")
    d.add_word("TODO", day="2026-11-25")
    f = d.facts("2026-11-25")
    assert "2,5 Stunden" in f and "2 Wörter gefressen" in f and "TODO" in f
    assert "Commits" not in f
    assert d.summary(d.data["days"]["2026-11-25"]) == "⏱ 2,5 h · 🍪 2"


def test_week_review_due_after_two_entries(tmp_path):
    d = _d(tmp_path)
    d.set_entry("2026-11-23", "Montag war lang.")
    fri = datetime(2026, 11, 27, 16, 30)
    assert d.due_week(fri) is None                          # nur ein Eintrag
    d.set_entry("2026-11-25", "Mittwoch: viel gefressen.")
    assert d.due_week(datetime(2026, 11, 26, 10, 0)) is None  # Donnerstag: noch nicht
    assert d.due_week(fri) == "2026-11-23"
    d.set_week("2026-11-23", "Gute Woche.")
    assert d.due_week(fri) is None
    # nächste Woche wird die vergangene nicht nochmal geschrieben
    assert d.due_week(datetime(2026, 11, 30, 9, 0)) is None
    html = d.html("Pieps")
    assert "Wochenrückblick" in html and html.index("Wochenrückblick") < html.index("Mittwoch: viel")


def test_html_escapes_and_empty_book(tmp_path):
    d = _d(tmp_path)
    assert "Noch leer" in d.html("Pieps")
    d.set_entry("2026-11-25", "<b>frech</b> & so")
    assert "&lt;b&gt;frech" in d.html("Pieps")


def test_clean_strips_headings_but_keeps_text():
    out = diary.clean("## Tagebucheintrag:\n**Heute** hab ich drei Bugs gefressen.\n„Mampf!“")
    assert out.startswith("Heute hab ich") and "**" not in out and "Tagebucheintrag" not in out
    assert diary.clean("Tagebuch, du glaubst nicht, was heute los war.").startswith("Tagebuch, du")


def test_prompts_contain_facts_and_no_examples():
    prof = {"name": "Pieps", "creature": "spatz", "personality": "aengstlich", "persona": "Mag Semikolons."}
    system, user = personas.diary_prompt(prof, "Mittwoch, 25.11.2026", "- 3 Commits", previous="Gestern war ruhig.")
    assert "Pieps" in system and "Semikolons" in system and "- 3 Commits" in user and "Gestern war ruhig" in user
    system, user = personas.week_prompt(prof, "Woche vom 23.11.", [("Montag", "lang")], "⎇ 3")
    assert "Montag: lang" in user and "Highlight" in user


def test_reactions_count_commit_once(qapp):
    from claude_pet.reactions import Reactions

    class Ctl:
        def __init__(self):
            self.diary = diary.Diary("unused.json")
    r = Reactions.__new__(Reactions)
    r.ctl, r.diary_t = Ctl(), {}
    r._count_for_diary([("commit", "git commit -m x"), ("commit", "[main abc1234] x")])
    r._count_for_diary([("commit", "nochmal")])
    r._count_for_diary([("error", "Error: x")])
    day = r.ctl.diary._day()
    assert day["commits"] == 1 and day["errors"] == 1


# ------------------------------------------------------------ Träume
def test_dreams_come_while_sleeping_and_stop_on_waking():
    import random
    from claude_pet import dreams
    d = dreams.Dreamer(random.Random(3))
    got = [d.step(0.1, True, "katze", "verspielt", {"balls": 3}) for _ in range(600)]   # 60 s Schlaf
    icons = [g for g in got if g]
    assert 2 <= len(icons) <= 4, icons                       # ca. alle 20 s ein Traum
    assert got.index(icons[0]) * 0.1 >= dreams.FIRST_AFTER - 0.1
    assert d.step(0.1, False, "katze", "verspielt", {}) is None and d.current is None and d.alpha() == 0


def test_dream_choice_follows_the_day():
    import random
    from claude_pet import dreams
    rnd = random.Random(1)
    many = [dreams.pick("geist", "faul", {"balls": 5}, rnd) for _ in range(400)]
    calm = [dreams.pick("geist", "faul", {}, rnd) for _ in range(400)]
    assert many.count("ball") > 3 * max(1, calm.count("ball"))
    assert dreams.pick("katze", "faul", {}, random.Random(5)) in dreams.ICONS
    assert all(len(r) == 7 for rows, _ in dreams.ICONS.values() for r in rows)
    assert set(dreams.LABEL) == set(dreams.ICONS)


def test_dreams_end_up_in_diary_facts(tmp_path):
    d = _d(tmp_path)
    d.add_dream("Ball", day="2026-11-25")
    d.add_dream("Ball", day="2026-11-25")
    assert d.facts("2026-11-25").count("Ball") == 1 and "geträumt" in d.facts("2026-11-25")
    assert d.summary(d.data["days"]["2026-11-25"]) == ""
