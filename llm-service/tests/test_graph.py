from dataclasses import dataclass
@dataclass
class Alumni:
    id: int
    like: int
    # for graph traversal, to mark if the node has been visited
    visited: bool 

def findCycle(alumni: Alumni, list_of_alumni: list) -> list:
    circle = []
    alumni_set = set() # to keep track of visited alumni ids in the current path
    cur = alumni # start with the given alumni
    while(not cur.visited):
        alumni_set.add(cur.id)
        circle.append(cur)
        cur.visited = True
        if (cur.like < 1 or cur.like > len(list_of_alumni)): # if like value is out of bounds, no cycle can be formed
            return [] # if like value is out of bounds, no cycle can be formed
        next = list_of_alumni[cur.like - 1] # move to the next alumni based on the like value, -1 for 0-based index
        cur = next

    # if we reach here, it means we've found a cycle
    if len(alumni_set) > 0 and (cur.id in alumni_set):
        # if we've seen this alumni before in the current path, we've found a cycle
        return circle
    else:
        return [] # if we haven't seen this alumni before, it means we've reached a visited node without forming a cycle
    

if __name__ == "__main__":
    print("Running graph tests...")
    count = int(input("Enter a number: "))
    # input alumni ids, split by spaces, convert to list of integers
    alumni_ids = list(map(int, input("Enter alumni ids (space separated): ").split()))
    # index as Alumni's id, value as Alumni's like, default visited as False, create a list of Alumni objects
    alumni_list = [Alumni(id=(i + 1), like=id, visited=False) for i,id in enumerate(alumni_ids)]
    # find cycles for each alumni in the list
    target_cycle = []
    for alumni in alumni_list:
        if not alumni.visited: # only find cycle for unvisited alumni
            cycle = findCycle(alumni, alumni_list)
            print(f"Cycle found: {[a.id for a in cycle]}")
            if len(cycle) > len(target_cycle): # update target cycle if current cycle is longer
                target_cycle = cycle
    
    print(f"Longest cycle: {[a.id for a in target_cycle]}")