import argparse
import sys
from datetime import datetime, timedelta

import gnucash
from gnucash import Session
from gnucash.gnucash_business import Invoice

def find_account_by_path(root, path):
    """Finds an account by its full path, splitting by ':'."""
    acc = root
    for part in path.split(':'):
        acc = acc.lookup_by_name(part)
        if not acc:
            return None
    return acc

def gdate_to_datetime(gdate):
    """Converts a GnuCash GDate to a Python datetime object."""
    return datetime(gdate.year, gdate.month, gdate.day)


def get_all_invoices(book, is_paid=None, is_active=None):
    """Returns a list of all invoices in the book.
    Posts a query to search for all invoices.
    arguments:
    book the gnucash book to work with
    keyword-arguments:
    is_paid int 1 to search for invoices having been paid, 0 for not, None to ignore.
    is_active int 1 to search for active invoices
    """
    query = get_all_invoices_and_bills(book, is_paid, is_active)
    # return only invoices (1 = invoices)
    pred_data = gnucash.gnucash_core.QueryInt32Predicate(gnucash.QOF_COMPARE_EQUAL, 1)
    query.add_term([gnucash.INVOICE_TYPE], pred_data, gnucash.QOF_QUERY_AND)
    invoice_list = []
    for result in query.run():
        invoice_list.append(Invoice(instance=result))
    query.destroy()
    return invoice_list

def get_all_bills(book, is_paid=None, is_active=None):
    """Returns a list of all bills in the book.
    Posts a query to search for all bills.
    arguments:
    book the gnucash book to work with
    keyword-arguments:
    is_paid int 1 to search for bills having been paid, 0 for not, None to ignore.
    is_active int 1 to search for active bills
    """
    query = get_all_invoices_and_bills(book, is_paid, is_active)
    # return only bills (0 = bills)
    pred_data = gnucash.gnucash_core.QueryInt32Predicate(gnucash.QOF_COMPARE_EQUAL, 0)
    query.add_term([gnucash.INVOICE_TYPE], pred_data, gnucash.QOF_QUERY_AND)
    bill_list = []
    for result in query.run():
        bill_list.append(Invoice(instance=result))
    query.destroy()
    return bill_list

def get_all_invoices_and_bills(book, is_paid, is_active):
    query = gnucash.Query()
    query.search_for('gncInvoice')
    query.set_book(book)
    if is_paid == 0:
        query.add_boolean_match([gnucash.INVOICE_IS_PAID], False, gnucash.QOF_QUERY_AND)
    elif is_paid == 1:
        query.add_boolean_match([gnucash.INVOICE_IS_PAID], True, gnucash.QOF_QUERY_AND)
    elif is_paid == None:
        pass
    # active = JOB_IS_ACTIVE
    if is_active == 0:
        query.add_boolean_match(['active'], False, gnucash.QOF_QUERY_AND)
    elif is_active == 1:
        query.add_boolean_match(['active'], True, gnucash.QOF_QUERY_AND)
    elif is_active == None:
        pass
    return query

def main():
    """Main function to process GnuCash data."""
    parser = argparse.ArgumentParser(
        description="Automatically match payments to invoices or bills in a GnuCash file."
    )
    parser.add_argument("--gnucash_file", required=True, help="Path to the GnuCash file (.gnucash).")
    parser.add_argument(
        "--payment_account",
        required=True,
        help="Full name of the payment account (e.g., 'Assets:Current Assets:Checking Account')."
    )
    parser.add_argument("--mode", choices=['ar', 'ap'], required=True, help="Processing mode: 'ar' for invoices/receivables or 'ap' for bills/payables.")
    parser.add_argument("--ar_ap_account", required=True, help="Full name of the Accounts Receivable or Accounts Payable account.")
    args = parser.parse_args()

    try:
        session = Session(args.gnucash_file, is_new=False, force_lock=True)
    except Exception as e:
        print(f"Error opening GnuCash file: {e}", file=sys.stderr)
        sys.exit(1)

    book = session.book
    root = book.get_root_account()

    payment_account = find_account_by_path(root, args.payment_account)
    if not payment_account:
        print(f"Error: Could not find payment account '{args.payment_account}'", file=sys.stderr)
        session.end()
        sys.exit(1)

    ar_ap_account = find_account_by_path(root, args.ar_ap_account)
    if not ar_ap_account:
        print(f"Error: Could not find A/R or A/P account '{args.ar_ap_account}'", file=sys.stderr)
        session.end()
        sys.exit(1)

    changes_made = False
    processed_transactions = set()

    if args.mode == 'ar':
        unpaid_invoices = get_all_invoices(book, is_paid=0)
        print(f"Found {len(unpaid_invoices)} unpaid invoices.")

        for split in payment_account.GetSplitList():
            transaction = split.GetParent()
            if transaction.GetGUID() in processed_transactions:
                continue

            for other_split in transaction.GetSplitList():
                if other_split.GetAccount() == ar_ap_account and not other_split.GetLot():
                    payment_amount = other_split.GetValue().abs()
                    payment_date = transaction.GetDate().date()

                    for invoice in list(unpaid_invoices):
                        invoice_amount = invoice.GetTotal()
                        invoice_date = gdate_to_datetime(invoice.GetDatePosted()).date()
                        date_diff_days = (payment_date - invoice_date).days

                        if invoice_amount == payment_amount and -10 <= date_diff_days <= 30:
                            print(f"Matching payment on {payment_date} ({payment_amount}) to Invoice {invoice.GetID()} from {invoice_date}")
                            other_split.SetLot(invoice)
                            unpaid_invoices.remove(invoice)
                            changes_made = True
                            break
                    break
            processed_transactions.add(transaction.GetGUID())

    elif args.mode == 'ap':
        unpaid_bills = get_all_bills(book, is_paid=0)
        print(f"Found {len(unpaid_bills)} unpaid bills.")

        for split in payment_account.GetSplitList():
            transaction = split.GetParent()
            if transaction.GetGUID() in processed_transactions:
                continue

            for other_split in transaction.GetSplitList():
                if other_split.GetAccount() == ar_ap_account and not other_split.GetLot():
                    payment_amount = other_split.GetValue()
                    payment_date = transaction.GetDate().date()

                    for bill in list(unpaid_bills):
                        bill_amount = bill.GetTotal()
                        bill_date = gdate_to_datetime(bill.GetDatePosted()).date()
                        date_diff_days = (payment_date - bill_date).days

                        if bill_amount == payment_amount and -10 <= date_diff_days <= 30:
                            print(f"Matching payment on {payment_date} ({payment_amount}) to Bill {bill.GetID()} from {bill_date}")
                            other_split.SetLot(bill)
                            unpaid_bills.remove(bill)
                            changes_made = True
                            break
                    break
            processed_transactions.add(transaction.GetGUID())

    if changes_made:
        print("Saving changes...")
        session.save()
    else:
        print("No new matches found.")

    session.end()
    print("Done.")

if __name__ == "__main__":
    main()
