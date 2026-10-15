from src.schedule import active_services, schedule

def test_no_local_feed_yet():
    assert isinstance(active_services('2026-10-15'),set)
    assert isinstance(schedule('2026-10-15','NONEXISTENT'),list)
