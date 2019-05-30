with open("cmp1.txt", "r") as f:
    str1 = f.read()

with open("cmp2.txt", "r") as f:
    str2 = f.read()

lines1 = str1.split("\n")
lines2 = str2.split("\n")

for l in list(lines1):
    if l in lines2:
        lines1.remove(l)
        lines2.remove(l)

with open("res1.txt", "w") as f:
    f.write("\n".join(lines1))

with open("res2.txt", "w") as f:
    f.write("\n".join(lines2))
