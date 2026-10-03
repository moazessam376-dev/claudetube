from ctube import promos

LESSON = "Now grab the vertex and of course scale it down a little, of course."


def test_course_pitch_is_found():
    paras = [
        (0, LESSON),
        (30, "These are techniques I go into in my course called the beginners academy."),
        (60, "So if you're interested, the link for that is beneath this video."),
        (90, LESSON),
    ]
    assert promos.find(paras, 120) == [(30.0, 90.0)]


def test_donation_appeal_with_one_quiet_paragraph_inside():
    paras = [
        (0, LESSON),
        (10, "They lack the funds to develop it."),
        (20, "So please donate if you can."),
        (30, "This lets more people try it."),
        (40, "The link is underneath this video, click that and make a donation."),
        (50, LESSON),
    ]
    assert promos.find(paras, 60) == [(10.0, 50.0)]


def test_lesson_mentions_are_not_promos():
    paras = [
        (0, LESSON),
        (10, "If you get stuck, use my guide. Link is in the description."),
        (20, LESSON),
        (30, "If more people donate, we can have good physics in Blender."),
        (40, "That is a discount from 145 dollars, by the way."),
    ]
    assert promos.find(paras, 50) == []


def test_sponsor_read():
    paras = [(0, "This video is sponsored by Acme. Use code TUBE for 10% off, link in the description."),
             (20, LESSON)]
    assert promos.find(paras, 40) == [(0.0, 20.0)]


def test_sponsor_chapter_title():
    chapters = [{"start_time": 0, "title": "Intro"}, {"start_time": 60, "title": "Sponsor: Acme"},
                {"start_time": 90, "title": "Modelling"}]
    assert promos.find([(0, LESSON)], 300, chapters) == [(60.0, 90.0)]


def test_inside():
    segs = [(10.0, 20.0)]
    assert promos.inside(10, segs) and promos.inside(19.9, segs)
    assert not promos.inside(20, segs) and not promos.inside(5, segs)
