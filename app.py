#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime

import gnucash
from gnucash import Session, SessionOpenMode
from gnucash.gnucash_business import Invoice
from gnucash.gnucash_core_c import qof_log_set_level, qof_log_init_filename
from gnucash.gnucash_core_c import GNC_INVOICE_CUST_INVOICE, GNC_INVOICE_VEND_INVOICE

#  The below doesn't seem to work. We still try it tho.
qof_log_set_level("", gnucash.gnucash_core_c.QOF_LOG_ERROR)
qof_log_init_filename("./gnucash-matcher.log")

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
    pred_data = gnucash.gnucash_core.QueryInt32Predicate(gnucash.QOF_COMPARE_EQUAL, GNC_INVOICE_CUST_INVOICE)
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
    pred_data = gnucash.gnucash_core.QueryInt32Predicate(gnucash.QOF_COMPARE_EQUAL, GNC_INVOICE_VEND_INVOICE)
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
    parser.add_argument("--days_before", type=int, default=None, help="Number of days the document date can be after the payment date. For date filtering, both --days_before and --days_after must be specified.")
    parser.add_argument("--days_after", type=int, default=None, help="Number of days the document date can be before the payment date. For date filtering, both --days_before and --days_after must be specified.")
    parser.add_argument("--dry_run", action="store_true", help="Perform a dry run without saving any changes.")
    parser.add_argument("--confirm", action="store_true", help="Confirm each match manually.")
    args = parser.parse_args()

    try:
        session = Session(args.gnucash_file, mode=SessionOpenMode.SESSION_NORMAL_OPEN)
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
        unpaid_docs = get_all_invoices(book, is_paid=0)
        print(f"Found {len(unpaid_docs)} unpaid invoices.")
        doc_type_str = "Invoice"
    elif args.mode == 'ap':
        unpaid_docs = get_all_bills(book, is_paid=0)
        print(f"Found {len(unpaid_docs)} unpaid bills.")
        doc_type_str = "Bill"

    match_counter = 0
    for split in payment_account.GetSplitList():
        transaction = split.GetParent()
        if transaction.GetGUID() in processed_transactions:
            continue

        splits = transaction.GetSplitList()

        # Ensure there are exactly two splits (one for the payment account and one for the other account)
        if len(splits) != 2:
            continue
        
        for other_split in splits:
            # Find the split that is not in the payment account and does not have a lot assigned.
            if other_split.GetAccount().Equal(ar_ap_account, False) and not other_split.GetLot():
                payment_amount = other_split.GetValue().abs()
                payment_date = transaction.GetDate().date()

                # Loop though the unpaid docs (either invoices or bills)
                for doc in list(unpaid_docs):
                    doc_amount = doc.GetTotal()
                    doc_date = gdate_to_datetime(doc.GetDatePosted()).date()
                    date_diff_days = (payment_date - doc_date).days

                    if args.days_before is not None and args.days_after is not None:
                        date_condition = -args.days_before <= date_diff_days <= args.days_after
                    else:
                        date_condition = True

                    if doc_amount.equal(payment_amount) and date_condition:
                        # Get the posted lot of the document. This is where gnucash keeps track of the open balance.
                        postedLot = doc.GetPostedLot()
                        # All splits assigned to the lot must belong to the same account.
                        if postedLot.get_account().Equal(ar_ap_account, False):
                            # This is a potential match.
                            do_match = False
                            if args.confirm:
                                owner = doc.GetOwner()
                                company_name = owner.GetName() if owner else "N/A"
                                print("-" * 20)
                                print("Potential match found:")
                                print("  Transaction details:")
                                print(f"    Description: {transaction.GetDescription()}")
                                print(f"    Date: {payment_date}")
                                print(f"    Amount: {payment_amount}")
                                print(f"  {doc_type_str} details:")
                                print(f"    ID: {doc.GetID()}")
                                billing_id = doc.GetBillingID()
                                if billing_id:
                                    print(f"    Billing ID: {billing_id}")
                                print(f"    Company: {company_name}")
                                print(f"    Date: {doc_date}")
                                print(f"    Amount: {doc_amount}")

                                choice = input("Match this? [y/N]: ").lower()
                                if choice == 'y':
                                    do_match = True
                            else:
                                do_match = True

                            if do_match:
                                # This is a match!
                                match_counter += 1
                                print(f"[{match_counter}] Matching payment on {payment_date} ({payment_amount}) to {doc_type_str} {doc.GetID()} ({doc_amount}) from {doc_date}")
                                if not args.dry_run:
                                    # Assign the split to the lot.
                                    other_split.AssignToLot(doc.GetPostedLot())
                                    # Mark that we made changes. So that we can save the session later.
                                    changes_made = True
                                # Remove the document from the list of unpaid documents. We don't consider multiple payments to the same document.
                                unpaid_docs.remove(doc)
                        break
                break
        processed_transactions.add(transaction.GetGUID())

    if args.dry_run:
        print(f"DRY RUN: Found {match_counter} potential matches. No changes will be saved.")
    elif changes_made:
        print(f"{match_counter} Matches found.")
        print("Saving changes...")
        session.save()
    else:
        print("No new matches found.")

    session.end()
    print("Done.")

if __name__ == "__main__":
    main()
