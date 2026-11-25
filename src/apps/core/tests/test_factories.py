import pytest

from apps.factories import (
    AchievementFactory,
    ChecklistItemFactory,
    DayCodeFactory,
    DayFactory,
    DecisionFactory,
    EntryFactory,
    GoalFactory,
    LoginAttemptFactory,
    MemberFactory,
    OpenQuestionFactory,
    ProjectFactory,
    RawMessageFactory,
    SiteConfigFactory,
    TelegramContactFactory,
    TimelineEventFactory,
)


@pytest.mark.django_db
def test_factories_create_every_model() -> None:
    config = SiteConfigFactory()
    member = MemberFactory()
    goal = GoalFactory(member=member)
    contact = TelegramContactFactory(member=member, tg_id=-1001234567890)
    code = DayCodeFactory()
    attempt = LoginAttemptFactory()
    day = DayFactory()
    entry = EntryFactory(member=member, day=day, kind="evening")
    message = RawMessageFactory(member=member, chat_id=-1001234567890)
    event = TimelineEventFactory(day=day)
    achievement = AchievementFactory()
    project = ProjectFactory()
    item = ChecklistItemFactory()
    decision = DecisionFactory(owners=[member])
    question = OpenQuestionFactory()
    assert config.pk == 1
    assert goal.member_id == member.pk
    assert contact.tg_id == -1001234567890
    assert code.pk and attempt.pk and entry.pk and message.pk
    assert event.pk and achievement.pk and item.pk
    assert project.pk == 1
    assert list(decision.owners.all()) == [member]
    assert question.pk
