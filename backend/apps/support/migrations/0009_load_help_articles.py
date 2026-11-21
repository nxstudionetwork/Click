from django.db import migrations


def load(apps, schema_editor):
    from apps.support.articles import ARTICLES

    HelpArticle = apps.get_model("support", "HelpArticle")
    for i, (slug, cat, title, summary, body, steps, keywords, action, popular) in enumerate(ARTICLES):
        HelpArticle.objects.update_or_create(slug=slug, defaults=dict(
            category=cat, title=title, summary=summary, body=body, steps=steps, keywords=keywords, position=i, is_popular=popular,
            action_label=action[0] if action else "", action_path=action[1] if action else "", is_published=True))


class Migration(migrations.Migration):
    dependencies = [("support", "0008_helparticle_supportticket_issue_type_and_more")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
