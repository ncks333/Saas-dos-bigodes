# Trial Countdown in Dashboard

## Goal

Show an active trial user how many whole calendar days remain before the trial ends.

## Behavior

1. Backend exposes authenticated subscription status and `trial_ends_at` for the current barbershop.
2. Dashboard shows `Teste grátis: faltam X dias` at its top when status is `TRIAL`.
3. The browser calculates `X` from `trial_ends_at`, never below zero.
4. The notice is absent for active, grace, suspended, canceled, and pending subscriptions.

## Scope

No changes to billing dates, access control, checkout, or payment collection.

## Tests

Cover API data for the current tenant and dashboard rendering for a trial, including zero remaining days.
