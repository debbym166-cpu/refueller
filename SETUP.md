# LitreVault – what's new in this version

File and folder names are exactly the same as in your original project.
There is no payment provider for now: clicking **Pay** completes the purchase straight away
and the litres appear in the wallet.

## Run
1. (optional, for the QR image) `pip install segno`
2. `python manage.py migrate`
3. `python manage.py runserver`
4. In `/admin/` add a **Fuel Price** (otherwise ₦980/L is used) and at least one **Station**.

## Fuel is deducted when an attendant confirms
Admin → Fuel redemptions → select → action "Confirm selected redemptions".

## New files (nothing of yours was renamed)
portfolio/services.py, portfolio/context_processors.py, templates/partials/messages.html,
templates/price-history.html, templates/qr-redemption.html, portfolio/migrations/0003 and 0004.
Tests: `python manage.py test`
