package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationTopoguideAdvancedSearch extends Simulation {

        val httpProtocol = http
                .inferHtmlResources(C2corgConf.black_list, WhiteList())
                .acceptHeader("*/*")
                .acceptEncodingHeader("gzip, deflate")

        val scn = scenario("ConsultationTopoguideAdvancedSearch")
                .exec(Homepage.init)
                .pause(4)
                .exec(Route.advancedSearchInit)
                .pause(5)
                .exec(Route.advancedSearch)
                .pause(5)
                .exec(Route.view)

        setUp(scn.inject(rampUsers(C2corgConf.num_users) over (C2corgConf.ramp_time_seconds seconds))).protocols(httpProtocol)
}
