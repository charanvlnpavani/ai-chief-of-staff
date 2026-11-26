"""Built-in roadmaps, written for Personal OS (not copied from any third-party roadmap).

Each day is (level, [(title, detail, minutes), ...]). Days are numbered in order from 1.
"""

from dataclasses import dataclass

Task = tuple[str, str, int]
Day = tuple[str, list[Task]]


@dataclass(frozen=True, slots=True)
class Template:
    key: str
    subject: str
    title: str
    aliases: frozenset[str]
    days: tuple[Day, ...]


def _learn(topic: str, detail: str, minutes: int = 30) -> Task:
    return (f"Learn: {topic}", detail, minutes)


def _solve(problems: str, detail: str, minutes: int = 45) -> Task:
    return (f"Solve: {problems}", detail, minutes)


DSA_DAYS: tuple[Day, ...] = (
    # ------------------------------------------------------------- basic
    (
        "basic",
        [
            _learn(
                "Big-O notation",
                "Count how many steps a loop, a nested loop and a halving "
                "loop take. Write the complexity of five small snippets you write yourself.",
            ),
            _solve("sum, max and average of an array", "Do it in one pass; state time and space."),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "arrays and in-place updates",
                "Indexing, copying vs. modifying in place, the cost of inserting in the middle.",
            ),
            _solve("reverse an array in place; move all zeros to the end", "Use two indexes."),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "strings and character counts",
                "Immutable strings, building output with a "
                "list, counting characters with a dictionary or a 26-slot array.",
            ),
            _solve("valid anagram; first non-repeating character", "Aim for O(n)."),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "hash maps and sets",
                "Average O(1) lookup, what a hash collision is, when a set beats a list.",
            ),
            _solve("two sum; contains duplicate", "First brute force, then the hash-map version."),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "the two-pointer pattern",
                "Pointers moving toward each other on sorted data, "
                "and a slow/fast pair for in-place filtering.",
            ),
            _solve(
                "pair with target sum in a sorted array; remove duplicates from a sorted array",
                "No extra array allowed.",
            ),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "the sliding-window pattern",
                "Fixed-size windows vs. windows that grow and "
                "shrink; what you add and remove at each step.",
            ),
            _solve(
                "max sum of a subarray of size k; longest substring without repeating characters",
                "Track the window with a set or a map.",
            ),
        ],
    ),
    (
        "basic",
        [
            _learn("prefix sums", "Precompute running totals so any range sum is one subtraction."),
            _solve("range sum query; count subarrays that sum to k", "Prefix sum plus a hash map."),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "recursion and the call stack",
                "Base case, recursive case, and drawing the call tree by hand.",
            ),
            _solve(
                "factorial, fibonacci, fast power x^n",
                "Then rewrite fibonacci without recursion and compare.",
            ),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "sorting",
                "Implement merge sort yourself; understand how quicksort "
                "partitions and why its worst case is O(n^2).",
                40,
            ),
            _solve("sort colours (0s, 1s, 2s); merge two sorted arrays", "One pass for colours."),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "binary search", "Loop invariants, lo/hi updates, and avoiding off-by-one errors."
            ),
            _solve(
                "classic binary search; first and last position of a value",
                "Write both bounds as separate searches.",
            ),
        ],
    ),
    (
        "basic",
        [
            _learn(
                "linked lists", "Nodes and pointers, a dummy head, why there is no random access."
            ),
            _solve("reverse a linked list; find the middle node", "Iterative reversal first."),
        ],
    ),
    (
        "basic",
        [
            _learn("stacks and queues", "LIFO vs. FIFO and the problems each one fits."),
            _solve(
                "valid parentheses; a queue built from two stacks",
                "Explain the amortised cost of the queue.",
            ),
        ],
    ),
    (
        "basic",
        [
            (
                "Review: redo three problems from this level",
                "Pick the three that felt hardest "
                "and solve them again without notes. Write one line on what tripped you up.",
                60,
            ),
        ],
    ),
    # ------------------------------------------------------------- intermediate
    (
        "intermediate",
        [
            _learn("fast and slow pointers", "Detecting a cycle and finding where it starts."),
            _solve("linked list cycle; merge two sorted lists", "Draw the pointers."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "the monotonic stack",
                "Keep the stack increasing or decreasing to find the "
                "next greater or smaller element in O(n).",
            ),
            _solve("next greater element; daily temperatures", "Store indexes, not values."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "binary search on the answer",
                "Search over possible answers when a yes/no check is monotonic.",
            ),
            _solve(
                "integer square root; minimum ship capacity to deliver within d days",
                "Write the check function first.",
            ),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "binary trees and traversals",
                "Pre-, in- and post-order, recursive and with an explicit stack.",
            ),
            _solve("all three traversals iteratively", "Compare with the recursive versions."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "thinking recursively about trees",
                "Ask what each subtree must return to its parent.",
            ),
            _solve("maximum depth; invert a tree; same tree", "Each in under 10 lines."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "binary search trees",
                "The ordering invariant and what in-order traversal gives you.",
            ),
            _solve("validate a BST; kth smallest element", "Pass min/max bounds down."),
        ],
    ),
    (
        "intermediate",
        [
            _learn("breadth-first search on trees", "A queue and processing one level at a time."),
            _solve("level-order traversal; right side view", "Use the queue length per level."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "heaps and priority queues",
                "Push/pop in O(log n); a size-k heap for top-k problems.",
            ),
            _solve("kth largest element; top k frequent elements", "Min-heap of size k."),
        ],
    ),
    (
        "intermediate",
        [
            _learn("backtracking", "Choose, explore, un-choose; drawing the decision tree."),
            _solve("all subsets; all permutations", "Count the outputs to check yourself."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "pruning in backtracking", "Stop exploring branches that cannot lead to an answer."
            ),
            _solve(
                "combination sum; generate valid parentheses",
                "Add pruning and measure the difference.",
            ),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "graphs: representation, BFS and DFS",
                "Adjacency lists vs. matrices, a visited set, grids as graphs.",
            ),
            _solve("number of islands; flood fill", "Do one with BFS and one with DFS."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "directed graphs and topological order",
                "In-degrees, Kahn's algorithm, detecting a cycle.",
            ),
            _solve("course schedule (can all courses be finished?)", "Then return the order."),
        ],
    ),
    (
        "intermediate",
        [
            _learn(
                "intervals and greedy choices",
                "Sort by start or end, then decide locally; how to argue a greedy choice is safe.",
            ),
            _solve("merge intervals; minimum meeting rooms", "Sort first."),
        ],
    ),
    (
        "intermediate",
        [
            (
                "Timed practice: two medium problems in 60 minutes",
                "Pick unseen problems from this level. Say your approach out loud before coding.",
                60,
            ),
        ],
    ),
    # ------------------------------------------------------------- advanced
    (
        "advanced",
        [
            _learn(
                "dynamic programming: memo to table",
                "State, transition, base case; turn a memoised recursion into a bottom-up table.",
                40,
            ),
            _solve("climbing stairs; house robber", "Both ways, then reduce space to O(1)."),
        ],
    ),
    (
        "advanced",
        [
            _learn(
                "1-D dynamic programming",
                "Choosing the state when the answer depends on earlier choices.",
            ),
            _solve("coin change; longest increasing subsequence", "O(n^2) first for LIS."),
        ],
    ),
    (
        "advanced",
        [
            _learn("grid dynamic programming", "dp[r][c] from the cells above and to the left."),
            _solve("unique paths; minimum path sum", "Then do it with one row of memory."),
        ],
    ),
    (
        "advanced",
        [
            _learn(
                "dynamic programming on two strings",
                "A 2-D table where each cell compares two prefixes.",
            ),
            _solve("longest common subsequence; edit distance", "Fill a small table by hand."),
        ],
    ),
    (
        "advanced",
        [
            _learn(
                "knapsack-style dynamic programming", "Take or skip each item; 0/1 vs. unbounded."
            ),
            _solve("0/1 knapsack; partition into two equal-sum subsets", "Spot the knapsack."),
        ],
    ),
    (
        "advanced",
        [
            _learn(
                "shortest paths with Dijkstra",
                "Why a min-heap works and why negative edges break it.",
                40,
            ),
            _solve("network delay time", "Then trace it on a 5-node graph by hand."),
        ],
    ),
    (
        "advanced",
        [
            _learn("union-find (disjoint sets)", "Union by rank and path compression."),
            _solve(
                "redundant connection; number of connected components", "Implement it from memory."
            ),
        ],
    ),
    (
        "advanced",
        [
            _learn("minimum spanning trees", "Kruskal (sort edges + union-find) and Prim (heap)."),
            _solve("minimum cost to connect all points", "Try both algorithms."),
        ],
    ),
    (
        "advanced",
        [
            _learn("tries", "Prefix trees for words; insert, search, starts-with."),
            _solve(
                "implement a trie; replace words with their shortest root", "Use a dict per node."
            ),
        ],
    ),
    (
        "advanced",
        [
            _learn(
                "harder tree problems",
                "Lowest common ancestor; turning a tree into a string and back.",
            ),
            _solve("lowest common ancestor; serialize and deserialize a tree", "Handle nulls."),
        ],
    ),
    (
        "advanced",
        [
            _learn("bit manipulation", "AND, OR, XOR, shifts; checking and setting bits."),
            _solve("single number; counting bits", "Explain why XOR works."),
        ],
    ),
    (
        "advanced",
        [
            _learn("monotonic deque", "Keep candidates in a deque to get window max/min in O(n)."),
            _solve("sliding window maximum", "Compare with the heap solution."),
        ],
    ),
    (
        "advanced",
        [
            _learn(
                "Fenwick and segment trees", "Range queries with point updates in O(log n).", 45
            ),
            _solve("range sum with updates", "Implement a Fenwick tree."),
        ],
    ),
    (
        "advanced",
        [
            (
                "Timed practice: one hard problem in 45 minutes",
                "Unseen problem from this level. "
                "Afterwards, write the key insight in one sentence.",
                60,
            ),
        ],
    ),
    # ------------------------------------------------------------- pro
    (
        "pro",
        [
            _learn("dynamic programming on trees", "Return several values from each subtree."),
            _solve(
                "binary tree maximum path sum; house robber on a tree",
                "Define what each call returns before coding.",
                60,
            ),
        ],
    ),
    (
        "pro",
        [
            _learn(
                "strongly connected components and bridges",
                "Kosaraju or Tarjan; low-link values.",
                45,
            ),
            _solve("critical connections in a network", "Trace low-link on paper first.", 60),
        ],
    ),
    (
        "pro",
        [
            _learn("string matching", "KMP's prefix function and rolling hashes.", 45),
            _solve("find a pattern in a text; longest happy prefix", "Use the prefix function."),
        ],
    ),
    (
        "pro",
        [
            _learn(
                "bitmask dynamic programming",
                "State = subset of items as a bitmask; works when n is about 20 or less.",
                45,
            ),
            _solve("shortest path visiting all nodes", "BFS over (node, mask).", 60),
        ],
    ),
    (
        "pro",
        [
            (
                "Hard set I: two hard problems",
                "For each, write the complexity and a short argument for why it is correct.",
                90,
            ),
        ],
    ),
    (
        "pro",
        [
            (
                "Build your pattern sheet",
                "List 15 patterns from this roadmap, each with how to "
                "recognise it and one example problem.",
                60,
            ),
        ],
    ),
    (
        "pro",
        [
            (
                "Virtual contest: four problems in 90 minutes",
                "Take a past contest under time pressure, then upsolve what you missed.",
                120,
            ),
        ],
    ),
    (
        "pro",
        [
            ("Hard set II: two hard problems", "Mix graphs and dynamic programming.", 90),
        ],
    ),
    (
        "pro",
        [
            (
                "Mock interview",
                "Two problems, explaining out loud the whole time. Record "
                "yourself and note one habit to fix.",
                75,
            ),
        ],
    ),
    (
        "pro",
        [
            (
                "Capstone: re-solve ten earlier problems cold",
                "One from each major pattern. Write down any gaps and plan a week to close them.",
                120,
            ),
        ],
    ),
)

TEMPLATES: dict[str, Template] = {
    "dsa": Template(
        key="dsa",
        subject="DSA",
        title="Data Structures & Algorithms: Basic to Pro",
        aliases=frozenset(
            {
                "dsa",
                "data structures",
                "algorithms",
                "data structures and algorithms",
                "data structures & algorithms",
                "algorithms and data structures",
                "leetcode",
            }
        ),
        days=DSA_DAYS,
    ),
}


def find_template(subject: str) -> Template | None:
    wanted = " ".join(subject.lower().split())
    return next((t for t in TEMPLATES.values() if wanted in t.aliases), None)
