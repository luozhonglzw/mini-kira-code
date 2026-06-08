def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        # 创建一个标志，用于判断列表是否已经排序完成
        already_sorted = True

        # 遍历整个列表，比较每对相邻的元素
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                # 如果元素顺序错误，则交换它们，并将已排序标志设置为 False
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                already_sorted = False

        # 如果在最近的一次遍历中没有进行任何交换，则列表已经排序完成
        if already_sorted:
            break

    return arr

# 示例使用
example_list = [64, 34, 25, 12, 22, 11, 90]
sorted_list = bubble_sort(example_list)
print("Sorted list:", sorted_list)