# 1 2 7 8
# 3 4 9 10
# 5 6 11 12 (End goal)

# Method 1: Using a pattern-based approach
for row in [0, 1, 2]:  # 3 rows
    for col in [0, 1, 2, 3]:  # 4 columns
        if col < 2:
            # First two columns: consecutive numbers
            num = row * 2 + col + 1
        else:
            # Last two columns: numbers starting from 7
            num = (row * 2 + col - 2) + 7
        print(num, end=' ')
    print()  # New line after each row