# GnuCash Matcher

This script automates the process of matching payments to invoices or bills in a GnuCash file. It can operate in either Accounts Receivable (AR) or Accounts Payable (AP) mode.

## Dependencies

- Python 3
- [python3-gnucash](https://wiki.gnucash.org/wiki/Python_Bindings#GnuCash)

In Debian based distributions like Ubuntu the easiest way to install the GnuCash Python bindings is via apt-get:

```bash
sudo apt-get install python3-gnucash
```

## Usage

The script is run from the command line and requires several arguments to specify the GnuCash file, accounts, and operating mode. In its simplest form the script matches _only_ on matching amounts. Other options are required to constrain the match to specific dates or text matches.

`./app.py --help` will show all available options.

### Basic command structure

```bash
./app.py --gnucash_file <path_to_file.gnucash> --payment_account <account_name> --mode <ar|ap> --ar_ap_account <account_name> [options]
```

### Arguments

- `--gnucash_file`: (Required) Path to your GnuCash file (e.g., `data.gnucash`).
- `--payment_account`: (Required) The full GnuCash account path for the account where payments are made or received (e.g., `"Assets:Current Assets:Checking Account"`).
- `--mode`: (Required) Set to `ar` for matching customer payments to invoices (Accounts Receivable) or `ap` for matching vendor payments to bills (Accounts Payable).
- `--ar_ap_account`: (Required) The full GnuCash account path for your Accounts Receivable or Accounts Payable account (e.g., `"Assets:Accounts Receivable"` or `"Liabilities:Accounts Payable"`).

### Options

- `--days_before <days>`: The number of days the document date can be after the payment date.
- `--days_after <days>`: The number of days the document date can be before the payment date. (Both `--days_before` and `--days_after` must be specified together for date filtering).
- `--match_id`: Constrain matches to transactions that contain the invoice/bill ID in their description.
- `--match_billing_id`: Constrain matches to transactions that contain the billing ID in their description.
- `--dry_run`: Perform a dry run without saving any changes. This is useful for previewing potential matches.
- `--confirm`: Ask for manual confirmation before matching each payment.

### Examples

**Accounts Receivable (AR) - Matching customer payments**

Match payments from your checking account to unpaid invoices, asking for confirmation for each match.

```bash
./app.py --gnucash_file mybook.gnucash \
         --payment_account "Assets:Current Assets:Checking Account" \
         --mode ar \
         --ar_ap_account "Assets:Accounts Receivable" \
         --confirm
```

**Accounts Payable (AP) - Matching payments to bills**

Perform a dry run to see potential matches for bills paid from your checking account.

```bash
./app.py --gnucash_file mybook.gnucash \
         --payment_account "Assets:Current Assets:Checking Account" \
         --mode ap \
         --ar_ap_account "Liabilities:Accounts Payable" \
         --dry_run
```

**Constrained Matching**

Match payments that occurred within a specific time window relative to the invoice date, and where the invoice ID is in the transaction description.

```bash
./app.py --gnucash_file mybook.gnucash \
         --payment_account "Assets:Current Assets:Checking Account" \
         --mode ar \
         --ar_ap_account "Assets:Accounts Receivable" \
         --days_before 5 \
         --days_after 5 \
         --match_id
```
