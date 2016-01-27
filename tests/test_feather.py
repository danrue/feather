from feather import feather
import pytest
import yaml

def test_000_schedule():
    with open("sources/test_000_schedule.yaml") as f:
        config = yaml.load(f.read())
    schedule = feather.backup_schedule(config['schedule'])
    assert 'monthly' in schedule
    assert 'weekly' in schedule
    assert 'daily' in schedule
    assert 'hourly' in schedule
    assert 'realtime' in schedule
    with pytest.raises(AssertionError):
        assert 'foo' in schedule

if __name__ == "__main__":
    test_000_schedule()
