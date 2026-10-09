package install

import "regexp"

var idPattern = regexp.MustCompile(`^[a-z][a-z0-9-]{0,63}$`)

func validID(id string) bool { return idPattern.MatchString(id) }
