import numpy as np


class RandomizationError(Exception):
    pass


def allocate_within_group(group_size: int, rng: np.random.Generator) -> np.ndarray:
    # Individual 1:1 allocation blocked within tutor group, methodology section 13.1.
    # Odd group sizes receive floor(m/2) or ceil(m/2) treated, direction chosen by the generator,
    # so no systematic imbalance accumulates across groups.
    if group_size < 2:
        raise RandomizationError(f"a tutor group needs at least 2 students to randomize, got {group_size}")

    half = group_size // 2
    if group_size % 2 == 0:
        n_treated = half
    else:
        n_treated = half + int(rng.integers(0, 2))

    assignment = np.zeros(group_size, dtype=np.int8)
    assignment[:n_treated] = 1
    rng.shuffle(assignment)
    return assignment


def assign_treatment(group_sizes: list[int], rng: np.random.Generator) -> np.ndarray:
    # Concatenated assignment vector over groups, in the order the groups are given.
    if not group_sizes:
        raise RandomizationError("no tutor groups to randomize")
    return np.concatenate([allocate_within_group(size, rng) for size in group_sizes])
