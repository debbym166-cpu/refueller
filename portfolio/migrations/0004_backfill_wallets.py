from django.db import migrations


def create_wallets(apps, schema_editor):
    User = apps.get_model("auth", "User")
    LitreWallet = apps.get_model("portfolio", "LitreWallet")
    for user in User.objects.all():
        LitreWallet.objects.get_or_create(user=user)


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0003_paystack_wallet_redemptions"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_wallets, migrations.RunPython.noop),
    ]
