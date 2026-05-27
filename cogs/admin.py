import random
doan = random.randint(1, 10)
i = 0
while True:
    i += 1
    so = int(input("nhap so: "))
    if so == doan:
        print(f"ban doan dung, ban doan {i} lan")
        break
    elif so >= doan:
        print("ban doan sai, thu so nho hon xem")
    else:
        print("ban doan sai, thu so lon hon xem")