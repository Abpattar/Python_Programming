# 1 2 7 8
# 3 4 9 10
# 5 6 11 12 (End goal)

for row in [0, 1, 2]: 
    for col in [0, 1, 2, 3]:  
        if col < 2:
            num = row * 2 + col + 1
        else: 
            num = (row * 2 + col - 2) + 7
        print(num, end=' ')
    print()  