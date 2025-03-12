import os

NUM_TO_MONTH = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

MONTH_TO_NUM = {month: num for num, month in NUM_TO_MONTH.items()}

def get_global_date():
    """
    Get the global date from global_date.txt
    
    Returns:
        dict: Dictionary with month and year
    """
    with open('../pbsoptimizer/global_date.txt', 'r') as f:
        lines = f.read().strip().split('\n')
    
    # If file has at least 4 lines, use the stored month and year
    if len(lines) >= 4:
        month = lines[2]
        year = int(lines[3])
    else:
        # Parse from the start date if month and year aren't explicitly stored
        start_date = lines[0]
        date_parts = start_date.split('-')
        month_num = int(date_parts[1])
        month = NUM_TO_MONTH.get(month_num, "None")
        year = int(date_parts[0])
    
    return {"month": month, "year": year}

def get_date_range():
    """
    Get the start and end date for the current global month/year
    
    Returns:
        tuple: (start_date, end_date) in YYYY-MM-DD format
    """
    date_info = get_global_date()
    month = date_info["month"]
    year = date_info["year"]
    
    month_num = MONTH_TO_NUM.get(month, 1)
    start_date = f"{year}-{month_num:02d}-01"
    
    end_day = 31 if month in ["Jan", "Mar", "May", "Jul", "Aug", "Oct", "Dec"] else 30
    if month == "Feb":
        end_day = 29 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 28
    
    end_date = f"{year}-{month_num:02d}-{end_day}"
    
    return start_date, end_date 